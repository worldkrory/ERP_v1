from __future__ import annotations

import logging
from datetime import date, datetime, timezone
from decimal import Decimal
from types import SimpleNamespace

from flask import Blueprint, jsonify, render_template, request
from flask_login import login_required, current_user
from sqlalchemy import or_
from sqlalchemy.exc import SQLAlchemyError

from app.extensions import db
from app.models.party import Party, PartyRole
from app.models.product import Product
from app.models.payment import Payment
from app.models.sale import Sale, SaleItem
from app.services.cloud_storage import CloudStorageError, upload_receipt
from app.models.unit import UnitOfMeasure
from app.auth.decorators import require_role, admin_only, audit_action
from app.services.sale_services import (
    SaleError,
    add_sale_item,
    create_sale,
    cancel_sale,
    resolve_sale_price,
)
from app.services.telegram_service import TelegramError, notify_sale, send_receipt

sales_bp = Blueprint("sales", __name__, url_prefix="/api/v1")
sales_admin_bp = Blueprint("sales_admin", __name__, template_folder="templates", url_prefix="")
logger = logging.getLogger(__name__)


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
            sale_number=str(payload.get("sale_number") or "V-AUTO"),
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


@sales_admin_bp.get("/ventas")
@login_required
@require_role("VENTAS", "ADMIN")
def sales_admin_page():
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
    except SQLAlchemyError:
        db.session.rollback()
        customers, products, units = _demo_catalog()
        demo_mode = True
    return render_template(
        "sales_admin.html",
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
        unit_catalog={unit.id: unit.display_name for unit in units},
        demo_mode=demo_mode,
        today=today.isoformat(),
        current_user=current_user,
    )


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
