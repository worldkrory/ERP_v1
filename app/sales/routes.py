from __future__ import annotations

import logging
from datetime import date, datetime, timezone
from decimal import Decimal
from types import SimpleNamespace

from flask import abort, redirect, url_for, Blueprint, jsonify, render_template, request
from flask_login import login_required, current_user
from sqlalchemy import func, or_, select
from sqlalchemy.orm import selectinload
from sqlalchemy.exc import SQLAlchemyError

from app.extensions import db
from app.models.party import Party, PartyRole
from app.models.product import Product
from app.models.payment import Payment, PaymentAllocation
from app.models.shipment import Shipment, ShipmentEvent, ShipmentItem
from app.models.sale import Sale, SaleItem, SaleItemBatch
from app.services.cloud_storage import CloudStorageError, upload_receipt
from app.models.unit import UnitOfMeasure
from app.utils.htmx import is_htmx_request

from app.models.batch import Batch
from app.models.inventory import InventoryBalance, InventoryLocation


from app.auth.decorators import require_role, admin_only, audit_action
from app.services.sale_services import (
    SaleError,
    add_sale_item,
    cancel_sale,
    confirm_sale_dispatch,
    create_sale,
    resolve_sale_price,
)
from app.services.telegram_service import TelegramError, notify_sale, send_receipt


sales_bp = Blueprint("sales", __name__, url_prefix="/api/v1")
sales_admin_bp = Blueprint("sales_admin", __name__, template_folder="templates", url_prefix="")
logger = logging.getLogger(__name__)

def _sale_detail_query(sale_id: int) -> Sale | None:
    """
    Obtiene una venta con todas las relaciones necesarias para el centro
    operativo, evitando consultas N+1 en templates.
    """
    statement = (
        select(Sale)
        .where(Sale.id == sale_id)
        .options(
            selectinload(Sale.party).selectinload(Party.addresses),
            selectinload(Sale.party).selectinload(Party.contacts),
            selectinload(Sale.salesperson),
            selectinload(Sale.shipping_address),
            selectinload(Sale.items).selectinload(SaleItem.product),
            selectinload(Sale.items).selectinload(SaleItem.unit),
            selectinload(Sale.items)
            .selectinload(SaleItem.batch_allocations)
            .selectinload(SaleItemBatch.batch),
            selectinload(Sale.items)
            .selectinload(SaleItem.batch_allocations)
            .selectinload(SaleItemBatch.location),
        )
    )

    return db.session.scalar(statement)

def _available_dispatch_batches(
    sale: Sale,
) -> dict[int, list[dict]]:
    """
    Construye las opciones de lote/ubicación para cada línea de una venta.

    No modifica inventario. Solo lee InventoryBalance con saldo positivo,
    Batch disponible y ubicación activa.
    """
    result: dict[int, list[dict]] = {}

    for item in sale.items:
        rows = db.session.execute(
            select(
                InventoryBalance,
                Batch,
                InventoryLocation,
            )
            .join(Batch, Batch.id == InventoryBalance.batch_id)
            .join(
                InventoryLocation,
                InventoryLocation.id == InventoryBalance.location_id,
            )
            .where(
                InventoryBalance.product_id == item.product_id,
                InventoryBalance.quantity_base > 0,
                Batch.status == "ACTIVE",
                InventoryLocation.is_active.is_(True),
            )
            .order_by(
                Batch.expiry_date.asc().nullslast(),
                Batch.production_date.asc().nullslast(),
                Batch.received_date.asc().nullslast(),
                Batch.id.asc(),
                InventoryLocation.name.asc(),
            )
        ).all()

        result[item.id] = [
            {
                "batch_id": batch.id,
                "batch_code": batch.batch_code,
                "batch_type": batch.batch_type,
                "batch_status": batch.status,
                "location_id": location.id,
                "location_code": location.code,
                "location_name": location.name,
                "location_display": location.display_name,
                "location_type": location.location_type,
                "available_quantity_base": Decimal(balance.quantity_base),
                "average_unit_cost": Decimal(balance.average_unit_cost),
                "total_value": Decimal(balance.total_value),
                "farm_name": batch.farm_name,
                "municipality_name": batch.municipality_name,
                "harvest_year": batch.harvest_year,
                "harvest_period": batch.harvest_period,
                "production_date": batch.production_date,
                "received_date": batch.received_date,
                "expiry_date": batch.expiry_date,
                "cupping_score": batch.cupping_score,
                "humidity_pct": batch.humidity_pct,
                "quality_notes": batch.quality_notes,
            }
            for balance, batch, location in rows
        ]

    return result

@sales_admin_bp.get("/ventas/<int:sale_id>/despacho")
@login_required
@require_role("VENTAS", "ADMIN")
def sale_dispatch_workspace(sale_id: int):
    """Sala de despacho final: solo ventas DRAFT."""

    sale = _sale_detail_query(sale_id)

    if sale is None:
        abort(404)

    if sale.status != "DRAFT":
        return redirect(
            url_for("sales_admin.sale_detail", sale_id=sale.id)
        )

    try:
        available_batches_by_item = _available_dispatch_batches(sale)
    except SQLAlchemyError:
        db.session.rollback()
        logger.exception(
            "No fue posible consultar inventario para despacho de venta %s",
            sale.id,
        )
        return (
            render_template(
                "sales/dispatch.html",
                sale=sale,
                available_batches_by_item={},
                dispatch_error=(
                    "No fue posible consultar los saldos disponibles. "
                    "Intenta nuevamente."
                ),
            ),
            500,
        )

    return render_template(
        "sales/dispatch.html",
        sale=sale,
        available_batches_by_item=available_batches_by_item,
        dispatch_error=None,
    )

@sales_admin_bp.post("/ventas/<int:sale_id>/despacho/confirmar")
@login_required
@require_role("VENTAS", "ADMIN")
@audit_action("CONFIRM_SALE_DISPATCH")
def confirm_sale_dispatch_route(sale_id: int):
    """
    Recibe todas las asignaciones del despacho y confirma la venta.

    El navegador envía JSON:
    {
      "items": [
        {
          "sale_item_id": 12,
          "allocations": [
            {
              "batch_id": 7,
              "location_id": 2,
              "quantity_base": "1.0000"
            }
          ]
        }
      ]
    }
    """
    sale = _sale_detail_query(sale_id)

    if sale is None:
        return jsonify({"error": "Venta no encontrada."}), 404

    payload = request.get_json(silent=True) or {}
    raw_items = payload.get("items")

    if not isinstance(raw_items, list) or not raw_items:
        return jsonify(
            {"error": "Debes enviar las asignaciones de despacho."}
        ), 400

    try:
        allocations_by_item: dict[int, list[dict]] = {}

        for raw_item in raw_items:
            item_id = int(raw_item["sale_item_id"])
            allocations = raw_item.get("allocations")

            if not isinstance(allocations, list) or not allocations:
                raise SaleError(
                    f"La línea {item_id} no tiene lotes asignados."
                )

            normalized_allocations = []

            for allocation in allocations:
                normalized_allocations.append(
                    {
                        "batch_id": int(allocation["batch_id"]),
                        "location_id": int(allocation["location_id"]),
                        "quantity_base": str(
                            Decimal(str(allocation["quantity_base"]))
                        ),
                    }
                )

            if item_id in allocations_by_item:
                raise SaleError(
                    "Una línea de venta aparece repetida en el despacho."
                )

            allocations_by_item[item_id] = normalized_allocations

        confirmed_sale = confirm_sale_dispatch(
            db.session,
            sale,
            allocations_by_item=allocations_by_item,
            created_by_id=current_user.id,
        )

        db.session.commit()
        _notify_sale_best_effort(confirmed_sale)

        return jsonify(
            {
                "ok": True,
                "sale_id": confirmed_sale.id,
                "sale_number": confirmed_sale.sale_number,
                "status": confirmed_sale.status,
                "payment_status": confirmed_sale.payment_status,
                "total": str(confirmed_sale.total),
                "cost_total": str(confirmed_sale.cost_total),
                "margin_amount": str(confirmed_sale.margin_amount),
                "margin_pct": (
                    str(confirmed_sale.margin_pct)
                    if confirmed_sale.margin_pct is not None
                    else None
                ),
                "detail_url": url_for(
                    "sales_admin.sale_detail",
                    sale_id=confirmed_sale.id,
                ),
            }
        )

    except (
        KeyError,
        TypeError,
        ValueError,
        SaleError,
    ) as exc:
        db.session.rollback()
        return jsonify({"error": str(exc)}), 400

    except SQLAlchemyError:
        db.session.rollback()
        logger.exception(
            "No fue posible confirmar despacho de venta %s",
            sale_id,
        )
        return jsonify(
            {"error": "No fue posible confirmar la salida de inventario."}
        ), 500

@sales_admin_bp.get("/ventas")
@login_required
@require_role("VENTAS", "ADMIN", "CONSULTA")
def sales_workspace():
    """Bandeja comercial definitiva de ventas."""

    today = date.today()

    filters = {
        "q": request.args.get("q", "").strip(),
        "status": request.args.get("status", "").strip(),
        "payment_status": request.args.get("payment_status", "").strip(),
        "channel": request.args.get("channel", "").strip(),
    }

    statement = (
        select(Sale)
        .options(selectinload(Sale.party))
        .order_by(Sale.sale_date.desc(), Sale.id.desc())
    )

    if filters["status"]:
        statement = statement.where(Sale.status == filters["status"])

    if filters["payment_status"]:
        statement = statement.where(
            Sale.payment_status == filters["payment_status"]
        )

    if filters["channel"]:
        statement = statement.where(Sale.channel == filters["channel"])

    if filters["q"]:
        term = f"%{filters['q']}%"

        statement = (
            statement
            .join(Party, Party.id == Sale.party_id)
            .where(
                or_(
                    Sale.sale_number.ilike(term),
                    Party.legal_name.ilike(term),
                    Party.trade_name.ilike(term),
                    Party.document_number.ilike(term),
                )
            )
        )

    sales = db.session.scalars(statement.limit(100)).all()

    metrics = {
        "draft_count": sum(sale.status == "DRAFT" for sale in sales),
        "confirmed_count": sum(
            sale.status in ("CONFIRMED", "DISPATCHED", "DELIVERED")
            for sale in sales
        ),
        "pending_collection": sum(
            (
                Decimal(sale.balance_due)
                for sale in sales
                if sale.status != "CANCELLED" and sale.balance_due > 0
            ),
            Decimal("0"),
        ),
        "overdue_count": sum(sale.is_overdue for sale in sales),
        "pending_dispatch_count": sum(
            sale.status == "CONFIRMED"
            for sale in sales
        ),
    }

    return render_template(
        "sales/index.html",
        sales=sales,
        metrics=metrics,
        filters=filters,
        today=today,
    )

@sales_admin_bp.get("/ventas/<int:sale_id>")
@login_required
@require_role("VENTAS", "ADMIN", "CONSULTA")
def sale_detail(sale_id: int):
    """Centro operativo de una venta."""

    sale = _sale_detail_query(sale_id)

    if sale is None:
        abort(404)

    return render_template(
        "sales/detail.html",
        sale=sale,
        today=date.today(),
    )



@sales_bp.post("/sales")
@login_required
@require_role("VENTAS", "ADMIN")
@audit_action("CREATE_SALE")
def create_sale_route():
    """Crear una nueva venta.
    
    Requiere:
    - Autenticación
    - Rol VENTAS o ADMIN
    """
    payload = request.get_json(silent=True) or {}
    try:
        sale = create_sale(
            db.session,
            sale_number=_next_sale_number(),
            party_id=int(payload["party_id"]),
            channel=str(payload.get("channel") or "RETAIL"),
            sale_date=(
                __import__("datetime").date.fromisoformat(payload["sale_date"])
                if payload.get("sale_date")
                else None
            ),
            salesperson_user_id=(
                int(payload["salesperson_user_id"])
                if payload.get("salesperson_user_id") is not None
                else None
            ),
            shipping_address_id=(
                int(payload["shipping_address_id"])
                if payload.get("shipping_address_id") is not None
                else None
            ),
        )
        for item_payload in payload.get("items", []):
            add_sale_item(
                db.session,
                sale,
                product_id=int(item_payload["product_id"]),
                quantity=Decimal(str(item_payload["quantity"])),
                unit_id=int(item_payload["unit_id"]),
                manual_unit_price=(
                    Decimal(str(item_payload["manual_unit_price"]))
                    if item_payload.get("manual_unit_price") not in (None, "")
                    else None
                ),
                discount_pct=Decimal(str(item_payload.get("discount_pct", "0"))),
            )
        db.session.commit()
        _notify_sale_best_effort(sale)
        return jsonify(_sale_payload(sale)), 201
    except SQLAlchemyError:
        db.session.rollback()
        return jsonify({"error": "La base de datos aún no está migrada."}), 503
    except (TypeError, ValueError, SaleError) as exc:
        db.session.rollback()
        return jsonify({"error": str(exc)}), 400


@sales_bp.post("/payments/<int:payment_id>/receipt")
@login_required
@require_role("VENTAS", "CONTABILIDAD", "ADMIN")
@audit_action("UPLOAD_PAYMENT_RECEIPT")
def upload_payment_receipt(payment_id: int):
    """Subir comprobante de pago.
    
    Requiere:
    - Autenticación
    - Rol VENTAS, CONTABILIDAD o ADMIN
    """
    payment = db.session.get(Payment, payment_id)
    if payment is None:
        return jsonify({"error": "Pago no encontrado."}), 404

    receipt = request.files.get("receipt")
    if receipt is None or not receipt.filename:
        return jsonify({"error": "Adjunta una imagen en el campo receipt."}), 400
    if not receipt.mimetype or not receipt.mimetype.startswith("image/"):
        return jsonify({"error": "El comprobante debe ser una imagen."}), 400

    try:
        receipt_url, public_id = upload_receipt(
            receipt,
            f"payment-{payment.id}-{int(datetime.now(timezone.utc).timestamp())}",
        )
        payment.receipt_url = receipt_url
        payment.receipt_public_id = public_id
        payment.receipt_uploaded_at = datetime.now(timezone.utc)
        payment.receipt_review_status = "UPLOADED"
        db.session.flush()

        message_id = None
        try:
            message_id = send_receipt(
                receipt_url,
                (
                    f"Comprobante para {payment.payment_number}\n"
                    f"Método: {payment.method}\n"
                    f"Monto: {payment.currency} {payment.amount:,.2f}\n"
                    f"Referencia: {payment.reference or 'Sin referencia'}\n"
                    "Estado: pendiente de revisión"
                ),
            )
            payment.telegram_message_id = message_id
            payment.receipt_review_status = "SENT"
        except TelegramError:
            # El comprobante queda disponible en Cloudinary aunque Telegram esté caído.
            pass

        db.session.commit()
        return jsonify(
            {
                "payment_id": payment.id,
                "receipt_url": payment.receipt_url,
                "telegram_message_id": message_id,
                "review_status": payment.receipt_review_status,
            }
        ), 201
    except CloudStorageError as exc:
        db.session.rollback()
        return jsonify({"error": str(exc)}), 503
    except (TypeError, ValueError) as exc:
        db.session.rollback()
        return jsonify({"error": str(exc)}), 400


@sales_bp.post("/sales/<int:sale_id>/items")
@login_required
@require_role("VENTAS", "ADMIN")
def add_sale_item_route(sale_id: int):
    """Agregar un item a una venta.
    
    Requiere:
    - Autenticación
    - Rol VENTAS o ADMIN
    """
    payload = request.get_json(silent=True) or {}
    sale = db.session.get(Sale, sale_id)
    if sale is None:
        return jsonify({"error": "Venta no encontrada."}), 404

    try:
        item = add_sale_item(
            db.session,
            sale,
            product_id=int(payload["product_id"]),
            quantity=Decimal(str(payload["quantity"])),
            unit_id=int(payload["unit_id"]),
            manual_unit_price=(
                Decimal(str(payload["manual_unit_price"]))
                if payload.get("manual_unit_price") is not None
                else None
            ),
            discount_pct=(
                Decimal(str(payload["discount_pct"]))
                if payload.get("discount_pct") is not None
                else Decimal("0")
            ),
        )
        db.session.commit()
        return jsonify(_item_payload(item)), 201
    except (TypeError, ValueError, SaleError) as exc:
        db.session.rollback()
        return jsonify({"error": str(exc)}), 400


@sales_bp.get("/sales")
@login_required
@require_role("VENTAS", "CONSULTA", "ADMIN")
def list_sales():
    """Listar todas las ventas.
    
    Requiere:
    - Autenticación
    - Rol VENTAS, CONSULTA o ADMIN
    """
    try:
        sales = db.session.scalars(db.select(Sale).order_by(Sale.sale_date.desc())).all()
        return jsonify([_sale_payload(sale) for sale in sales])
    except SQLAlchemyError:
        db.session.rollback()
        return jsonify(_demo_sales())


@sales_bp.get("/sales/price-preview")
@login_required
@require_role("VENTAS", "ADMIN")
def sale_price_preview():
    """Obtener preview de precios para un producto y cliente.
    
    Requiere:
    - Autenticación
    - Rol VENTAS o ADMIN
    """
    payload = request.args
    try:
        party = db.session.get(Party, int(payload["party_id"]))
        product = db.session.get(Product, int(payload["product_id"]))
        if party is None or product is None:
            raise SaleError("Cliente o producto no encontrado.")
        resolution = resolve_sale_price(
            db.session,
            party,
            product,
            int(payload["unit_id"]),
            Decimal(str(payload.get("quantity", "1"))),
            payload.get("channel", "RETAIL"),
            date.fromisoformat(payload.get("sale_date", date.today().isoformat())),
        )
        return jsonify(
            {
                "unit_price": str(resolution.unit_price),
                "price_source": resolution.price_source,
            }
        )
    except SQLAlchemyError:
        db.session.rollback()
        demo_prices = {101: "18000", 102: "32000", 103: "9500"}
        product_id = int(payload.get("product_id", 0))
        if product_id in demo_prices:
            return jsonify({"unit_price": demo_prices[product_id], "price_source": "DEMO"})
        return jsonify({"error": "La base de datos aún no está migrada."}), 503
    except (KeyError, TypeError, ValueError, SaleError) as exc:
        return jsonify({"error": str(exc)}), 400


@sales_bp.put("/sales/<int:sale_id>")
@login_required
@require_role("VENTAS", "ADMIN")
def update_sale_route(sale_id: int):
    """Actualizar información de una venta.
    
    Requiere:
    - Autenticación
    - Rol VENTAS o ADMIN
    """
    sale = db.session.get(Sale, sale_id)
    if sale is None:
        return jsonify({"error": "Venta no encontrada."}), 404

    payload = request.get_json(silent=True) or {}
    try:
        if payload.get("sale_number"):
            sale.sale_number = str(payload["sale_number"])
        if payload.get("channel"):
            sale.channel = str(payload["channel"])
        if payload.get("status"):
            sale.status = str(payload["status"])
        db.session.commit()
        return jsonify(
            {
                "id": sale.id,
                "sale_number": sale.sale_number,
                "party_id": sale.party_id,
                "channel": sale.channel,
                "status": sale.status,
                "total": str(sale.total),
            }
        )
    except (TypeError, ValueError, SaleError) as exc:
        db.session.rollback()
        return jsonify({"error": str(exc)}), 400


@sales_bp.delete("/sales/<int:sale_id>")
@login_required
@require_role("ADMIN", "VENTAS")
@audit_action("CANCEL_SALE")
def cancel_sale_route(sale_id: int):
    """Cancelar una venta.
    
    Características:
    - Solo DRAFT o CONFIRMED
    - Revierte automáticamente movimientos de inventario
    - Mantiene histórico para devoluciones futuras
    - Notifica a Telegram
    - Permite auditoría completa
    
    Requiere:
    - Autenticación
    - Rol ADMIN o VENTAS
    """
    sale = db.session.get(Sale, sale_id)
    if sale is None:
        return jsonify({"error": "Venta no encontrada."}), 404

    payload = request.get_json(silent=True) or {}
    reason = payload.get("reason", "Cancelado por el usuario")
    
    try:
        sale_number = sale.sale_number
        status_anterior = sale.status
        
        # Cancelar venta con notificación Telegram
        cancel_sale(
            db.session,
            sale,
            reason=reason,
            created_by_id=current_user.id if current_user.is_authenticated else None,
            notify_telegram=True,
            cancelled_by_name=current_user.email if current_user.is_authenticated else "Sistema"
        )
        db.session.commit()
        
        logger.info(
            f"Venta {sale_number} cancelada por usuario {current_user.email}. "
            f"Razón: {reason}",
            extra={"user_id": current_user.id, "sale_id": sale_id}
        )
        
        return jsonify({
            "cancelled": True,
            "id": sale_id,
            "sale_number": sale_number,
            "status_anterior": status_anterior,
            "status_nuevo": "CANCELLED",
            "razón": reason,
            "mensaje": f"Venta {sale_number} cancelada exitosamente. "
                      f"Puedes crear devoluciones referenciando esta venta."
        }), 200
        
    except SaleError as exc:
        db.session.rollback()
        logger.warning(
            f"Intento fallido de cancelar venta {sale_id}: {str(exc)}",
            extra={"user_id": current_user.id}
        )
        return jsonify({"error": str(exc)}), 409
    except Exception as exc:
        db.session.rollback()
        logger.error(
            f"Error inesperado al cancelar venta {sale_id}: {str(exc)}",
            extra={"user_id": current_user.id}
        )
        return jsonify({"error": "Error al cancelar la venta"}), 500

@sales_bp.get("/sales/<int:sale_id>/items/<int:item_id>/available-batches")
@login_required
@require_role("VENTAS", "ADMIN")
def available_sale_item_batches(sale_id: int, item_id: int):
    """
    Devuelve los saldos por lote y ubicación disponibles para una línea de venta.

    Solo se consulta para ventas DRAFT. No crea movimientos ni modifica saldo.
    """
    sale = db.session.get(Sale, sale_id)

    if sale is None:
        return jsonify({"error": "Venta no encontrada."}), 404

    if sale.status != "DRAFT":
        return jsonify(
            {"error": "Solo se pueden asignar lotes a ventas en borrador."}
        ), 409

    item = db.session.get(SaleItem, item_id)

    if item is None or item.sale_id != sale.id:
        return jsonify({"error": "Línea de venta no encontrada."}), 404

    try:
        rows = db.session.execute(
            select(
                InventoryBalance,
                Batch,
                InventoryLocation,
            )
            .join(Batch, Batch.id == InventoryBalance.batch_id)
            .join(
                InventoryLocation,
                InventoryLocation.id == InventoryBalance.location_id,
            )
            .where(
                InventoryBalance.product_id == item.product_id,
                InventoryBalance.quantity_base > 0,
                InventoryLocation.is_active.is_(True),
            )
            .order_by(
                Batch.received_date.asc(),
                Batch.id.asc(),
                InventoryLocation.name.asc(),
            )
        ).all()

        return jsonify(
            {
                "sale_id": sale.id,
                "item_id": item.id,
                "product_id": item.product_id,
                "required_quantity_base": str(item.quantity_base),
                "available_batches": [
                    {
                        "batch_id": batch.id,
                        "batch_code": batch.batch_code,
                        "batch_type": batch.batch_type,
                        "location_id": location.id,
                        "location_name": location.name,
                        "available_quantity_base": str(balance.quantity_base),
                        "unit_cost": str(balance.average_unit_cost),
                    }
                    for balance, batch, location in rows
                ],
            }
        )

    except SQLAlchemyError:
        db.session.rollback()
        logger.exception(
            "No fue posible consultar lotes disponibles para venta %s, línea %s",
            sale_id,
            item_id,
        )
        return jsonify(
            {"error": "No fue posible consultar los lotes disponibles."}
        ), 500

@sales_bp.post("/sales/<int:sale_id>/items/<int:item_id>/batch-allocations")
@login_required
@require_role("VENTAS", "ADMIN")
@audit_action("ALLOCATE_SALE_ITEM_BATCHES")
def allocate_sale_item_batches_route(sale_id: int, item_id: int):
    """
    Asigna lotes y ubicaciones a una línea en borrador.

    Esta operación crea los movimientos OUT_SALE, pero la venta continúa
    en DRAFT hasta llamar al endpoint de confirmación.
    """
    sale = db.session.get(Sale, sale_id)

    if sale is None:
        return jsonify({"error": "Venta no encontrada."}), 404

    if sale.status != "DRAFT":
        return jsonify(
            {"error": "Solo se pueden asignar lotes a ventas en borrador."}
        ), 409

    item = db.session.get(SaleItem, item_id)

    if item is None or item.sale_id != sale.id:
        return jsonify({"error": "Línea de venta no encontrada."}), 404

    payload = request.get_json(silent=True) or {}
    allocations = payload.get("allocations")

    if not isinstance(allocations, list) or not allocations:
        return jsonify(
            {"error": "Debes enviar al menos una asignación de lote."}
        ), 400

    try:
        rows = allocate_sale_item_batches(
            db.session,
            item,
            allocations=allocations,
            created_by_id=current_user.id,
        )
        db.session.commit()

        return jsonify(
            {
                "sale_id": sale.id,
                "item_id": item.id,
                "allocated_quantity_base": str(
                    sum(
                        (
                            Decimal(row.quantity_base)
                            for row in rows
                        ),
                        Decimal("0"),
                    )
                ),
                "required_quantity_base": str(item.quantity_base),
                "allocations": [
                    {
                        "id": row.id,
                        "batch_id": row.batch_id,
                        "location_id": row.location_id,
                        "quantity_base": str(row.quantity_base),
                        "unit_cost": str(row.unit_cost),
                        "total_cost": str(row.total_cost),
                        "movement_id": row.movement_id,
                    }
                    for row in rows
                ],
            }
        ), 201

    except (KeyError, TypeError, ValueError, SaleError) as exc:
        db.session.rollback()
        return jsonify({"error": str(exc)}), 400

    except SQLAlchemyError:
        db.session.rollback()
        logger.exception(
            "No fue posible asignar lotes a venta %s, línea %s",
            sale_id,
            item_id,
        )
        return jsonify(
            {"error": "No fue posible guardar la asignación de lotes."}
        ), 500

@sales_bp.post("/sales/<int:sale_id>/confirm")
@login_required
@require_role("VENTAS", "ADMIN")
@audit_action("CONFIRM_SALE")
def confirm_sale_route(sale_id: int):
    """
    Confirma una venta DRAFT previamente balanceada por lotes.

    La asignación de lotes ya creó movimientos OUT_SALE. Esta operación
    fija costos, margen y estado CONFIRMED.
    """
    sale = db.session.get(Sale, sale_id)

    if sale is None:
        return jsonify({"error": "Venta no encontrada."}), 404

    try:
        confirm_sale(db.session, sale)
        db.session.commit()

        _notify_sale_best_effort(sale)

        return jsonify(
            {
                "id": sale.id,
                "sale_number": sale.sale_number,
                "status": sale.status,
                "confirmed_at": (
                    sale.confirmed_at.isoformat()
                    if sale.confirmed_at
                    else None
                ),
                "subtotal": str(sale.subtotal),
                "tax_total": str(sale.tax_total),
                "total": str(sale.total),
                "cost_total": str(sale.cost_total),
                "margin_amount": str(sale.margin_amount),
                "margin_pct": (
                    str(sale.margin_pct)
                    if sale.margin_pct is not None
                    else None
                ),
            }
        ), 200

    except SaleError as exc:
        db.session.rollback()
        return jsonify({"error": str(exc)}), 409

    except SQLAlchemyError:
        db.session.rollback()
        logger.exception("No fue posible confirmar la venta %s", sale_id)
        return jsonify(
            {"error": "No fue posible confirmar la venta."}
        ), 500



@sales_admin_bp.get("/ventas/clasico")
@login_required
@require_role("VENTAS", "ADMIN")
def sales_admin_classic_page():
    """Panel de administración de ventas.
    
    Requiere:
    - Autenticación
    - Rol VENTAS o ADMIN
    """
    today = date.today()
    demo_mode = False
    try:
        customers = db.session.scalars(
            db.select(Party)
            .join(PartyRole, PartyRole.party_id == Party.id)
            .where(
                Party.is_active.is_(True),
                PartyRole.role_code == "CUSTOMER",
                PartyRole.valid_from <= today,
                or_(PartyRole.valid_to.is_(None), PartyRole.valid_to >= today),
            )
            .order_by(Party.legal_name)
        ).unique().all()
        products = db.session.scalars(
            db.select(Product)
            .where(Product.is_active.is_(True), Product.is_sellable.is_(True))
            .order_by(Product.name)
        ).all()
        units = db.session.scalars(
            db.select(UnitOfMeasure)
            .where(UnitOfMeasure.is_active.is_(True))
            .order_by(UnitOfMeasure.name)
        ).all()

        preview = SimpleNamespace(
            item_count=0,
            subtotal=Decimal("0"),
            discount_total=Decimal("0"),
            tax_total=Decimal("0"),
            total=Decimal("0"),
        )

    except SQLAlchemyError:
        db.session.rollback()
        customers, products, units = _demo_catalog()
        demo_mode = True
    return render_template(
        "sales/sales_admin.html",
        customers=customers,
        products=products,
        product_catalog=[
            {
                "id": product.id,
                "sku": product.sku,
                "name": product.name,
                "default_unit_id": product.effective_sales_unit_id,
                "unit_ids": sorted(
                    {
                        product.base_unit_id,
                        product.sales_unit_id,
                        *(
                            [conversion.from_unit_id for conversion in product.unit_conversions]
                            + [conversion.to_unit_id for conversion in product.unit_conversions]
                        ),
                    }
                    - {None}
                ),
            }
            for product in products
        ],
        units=units,
        unit_catalog={
            unit.id: unit.display_name
            for unit in units
        },
        preview=preview,
        demo_mode=demo_mode,
        today=today.isoformat(),
        current_user=current_user,
    )

@sales_admin_bp.get("/ventas/linea")
@login_required
@require_role("VENTAS", "ADMIN")
def sales_admin_line():
    """Devuelve una línea HTML de producto para HTMX."""

    today = date.today()

    try:
        products = db.session.scalars(
            db.select(Product)
            .where(
                Product.is_active.is_(True),
                Product.is_sellable.is_(True),
            )
            .order_by(Product.name)
        ).all()

        units = db.session.scalars(
            db.select(UnitOfMeasure)
            .where(UnitOfMeasure.is_active.is_(True))
            .order_by(UnitOfMeasure.name)
        ).all()
    except SQLAlchemyError:
        db.session.rollback()
        _, products, units = _demo_catalog()

    return render_template(
        "sales/partials/_sale_line.html",
        products=products,
        units=units,
        today=today.isoformat(),
        line_index=request.args.get("line_index", "0"),
    )

@sales_admin_bp.post("/ventas/previsualizar")
@login_required
@require_role("VENTAS", "ADMIN")
def sales_admin_preview():
    """Calcula un resumen visual de la venta sin guardarla."""

    quantities = request.form.getlist("quantity[]")
    prices = request.form.getlist("unit_price[]")
    discounts = request.form.getlist("discount_pct[]")

    subtotal = Decimal("0")
    discount_total = Decimal("0")

    for quantity_raw, price_raw, discount_raw in zip(
        quantities,
        prices,
        discounts,
    ):
        try:
            quantity = Decimal(quantity_raw or "0")
            unit_price = Decimal(price_raw or "0")
            discount_pct = Decimal(discount_raw or "0")

            gross = quantity * unit_price
            discount = gross * (discount_pct / Decimal("100"))

            subtotal += gross
            discount_total += discount
        except Exception:
            continue

    net_subtotal = subtotal - discount_total

    preview = SimpleNamespace(
        item_count=len(quantities),
        subtotal=subtotal,
        discount_total=discount_total,
        tax_total=Decimal("0"),
        total=net_subtotal,
    )

    return render_template(
        "sales/partials/_sale_summary.html",
        preview=preview,
    )

@sales_admin_bp.get("/ventas/tabla")
@login_required
@require_role("VENTAS", "CONSULTA", "ADMIN")
def sales_admin_table():
    """Devuelve la tabla HTML de ventas recientes."""

    try:
        sales = db.session.scalars(
            db.select(Sale)
            .order_by(Sale.sale_date.desc(), Sale.id.desc())
            .limit(30)
        ).all()
    except SQLAlchemyError:
        db.session.rollback()
        sales = [
            SimpleNamespace(**sale)
            for sale in _demo_sales()
        ]

    return render_template(
        "sales/partials/_sales_table.html",
        sales=sales,
    )

def _next_sale_number() -> str:
    """
    Genera un consecutivo interno de venta.

    Formato:
    V-YYYY-000001

    Es un número operacional interno; no corresponde a factura electrónica.
    """
    year = date.today().year
    prefix = f"V-{year}-"

    last_number = db.session.scalar(
        db.select(Sale.sale_number)
        .where(Sale.sale_number.like(f"{prefix}%"))
        .order_by(Sale.id.desc())
        .limit(1)
    )

    if not last_number:
        return f"{prefix}000001"

    try:
        sequence = int(last_number.rsplit("-", 1)[1])
    except (IndexError, ValueError):
        sequence = 0

    return f"{prefix}{sequence + 1:06d}"

def _demo_catalog() -> tuple[list, list, list]:
    units = [
        SimpleNamespace(id=1, display_name="Unidad (UN)"),
        SimpleNamespace(id=2, display_name="Libra (LB)"),
    ]
    products = [
        SimpleNamespace(id=101, sku="CAF-340", name="Café Bourbon Rosado 340 g", effective_sales_unit_id=1, base_unit_id=1, sales_unit_id=1, unit_conversions=[]),
        SimpleNamespace(id=102, sku="CAF-500", name="Café de finca 500 g", effective_sales_unit_id=1, base_unit_id=1, sales_unit_id=1, unit_conversions=[]),
        SimpleNamespace(id=103, sku="CAF-LB", name="Café tostado por libra", effective_sales_unit_id=2, base_unit_id=2, sales_unit_id=2, unit_conversions=[]),
    ]
    customers = [
        SimpleNamespace(id=1, display_name="Cafetería La Montaña", document_full="NIT DEMO-1"),
        SimpleNamespace(id=2, display_name="María Fernanda Torres", document_full="CC DEMO-2"),
    ]
    return customers, products, units


def _demo_sales() -> list[dict]:
    return [
        {"id": 1, "sale_number": "V-DEMO-001", "party_id": 1, "party_name": "Cafetería La Montaña", "channel": "CAFETERIA", "status": "DRAFT", "payment_status": "UNPAID", "sale_date": date.today().isoformat(), "subtotal": "64000.00", "tax_total": "0.00", "total": "64000.00", "items": []},
        {"id": 2, "sale_number": "V-DEMO-002", "party_id": 2, "party_name": "María Fernanda Torres", "channel": "RETAIL", "status": "CONFIRMED", "payment_status": "PAID", "sale_date": date.today().isoformat(), "subtotal": "18000.00", "tax_total": "0.00", "total": "18000.00", "items": []},
    ]


def _item_payload(item: SaleItem) -> dict:
    return {
        "id": item.id,
        "sale_id": item.sale_id,
        "product_id": item.product_id,
        "description": item.description,
        "quantity": str(item.quantity),
        "unit_id": item.unit_id,
        "unit_price": str(item.unit_price),
        "price_source": item.price_source,
        "discount_pct": str(item.discount_pct),
        "subtotal": str(item.subtotal),
        "tax_amount": str(item.tax_amount),
        "total": str(item.total),
    }


def _sale_payload(sale: Sale) -> dict:
    return {
        "id": sale.id,
        "sale_number": sale.sale_number,
        "party_id": sale.party_id,
        "party_name": sale.party.display_name if sale.party else "",
        "channel": sale.channel,
        "status": sale.status,
        "payment_status": sale.payment_status,
        "sale_date": sale.sale_date.isoformat(),
        "subtotal": str(sale.subtotal),
        "tax_total": str(sale.tax_total),
        "total": str(sale.total),
        "telegram_message_id": sale.telegram_message_id,
        "items": [_item_payload(item) for item in sale.items],
    }


def _notify_sale_best_effort(sale: Sale) -> None:
    try:
        message_id = notify_sale(sale)
    except TelegramError:
        logger.warning("No fue posible notificar la venta %s en Telegram", sale.sale_number)
        return

    sale.telegram_message_id = message_id
    sale.telegram_notified_at = datetime.now(timezone.utc)
    try:
        db.session.commit()
    except SQLAlchemyError:
        db.session.rollback()
        logger.exception("No fue posible guardar el mensaje Telegram de %s", sale.sale_number)
