from __future__ import annotations

from datetime import date
from decimal import Decimal

from flask import Blueprint, jsonify, render_template, request
from flask_login import current_user, login_required
from sqlalchemy import or_, select
from sqlalchemy.exc import SQLAlchemyError

from app.auth.decorators import audit_action, require_role
from app.extensions import db
from app.models.inventory import InventoryLocation
from app.models.party import DOCUMENT_TYPES, Party, PartyRole
from app.models.product import PRODUCT_KINDS, Product, ProductCategory
from app.models.purchase import Purchase, PurchaseItem
from app.models.unit import UnitConversion, UnitOfMeasure
from app.services.inventory_service import InventoryError, receive_purchase
from app.services.units import UnitConversionError, convert_quantity

purchases_bp = Blueprint("purchases", __name__, url_prefix="/api/v1")
purchases_admin_bp = Blueprint(
    "purchases_admin", __name__, template_folder="templates", url_prefix=""
)


@purchases_bp.get("/purchases/catalog")
@login_required
@require_role("INVENTARIO", "COMPRAS", "ADMIN", "CONSULTA")
def purchase_catalog():
    products = db.session.scalars(
        select(Product).where(Product.is_active.is_(True), Product.is_purchasable.is_(True)).order_by(Product.name)
    ).all()
    units = db.session.scalars(
        select(UnitOfMeasure).where(UnitOfMeasure.is_active.is_(True)).order_by(UnitOfMeasure.name)
    ).all()
    locations = db.session.scalars(
        select(InventoryLocation).where(InventoryLocation.is_active.is_(True)).order_by(InventoryLocation.name)
    ).all()
    suppliers = _supplier_query().all()
    return jsonify({
        "products": [_product_payload(product) for product in products],
        "units": [{"id": unit.id, "code": unit.code, "name": unit.name} for unit in units],
        "locations": [{"id": location.id, "code": location.code, "name": location.name} for location in locations],
        "suppliers": [{"id": party.id, "name": party.display_name, "document": party.document_full} for party in suppliers],
        "categories": [{"id": category.id, "name": category.name} for category in db.session.scalars(select(ProductCategory).where(ProductCategory.is_active.is_(True)).order_by(ProductCategory.name)).all()],
    })


@purchases_bp.post("/suppliers")
@login_required
@require_role("COMPRAS", "INVENTARIO", "ADMIN")
@audit_action("CREATE_SUPPLIER")
def create_supplier_route():
    payload = request.get_json(silent=True) or {}
    try:
        document_type = str(payload.get("document_type") or "CC")
        document_number = str(payload.get("document_number") or "").strip()
        legal_name = str(payload.get("legal_name") or "").strip()
        if document_type not in DOCUMENT_TYPES or not document_number or not legal_name:
            raise ValueError("Tipo de documento, número y nombre son obligatorios.")
        if document_type == "NIT" and payload.get("verification_digit") in (None, ""):
            raise ValueError("El NIT necesita dígito de verificación.")
        party = Party(
            party_type=str(payload.get("party_type") or "NATURAL"),
            document_type=document_type,
            document_number=document_number,
            verification_digit=(int(payload["verification_digit"]) if payload.get("verification_digit") not in (None, "") else None),
            legal_name=legal_name,
            first_name=str(payload.get("first_name") or "").strip() or None,
            last_name=str(payload.get("last_name") or "").strip() or None,
            email=str(payload.get("email") or "").strip() or None,
            phone=str(payload.get("phone") or "").strip() or None,
        )
        party.party_roles = [
            PartyRole(role_code="SUPPLIER", valid_from=date.today()),
            *([PartyRole(role_code="COFFEE_GROWER", valid_from=date.today())] if payload.get("is_coffee_grower") else []),
        ]
        db.session.add(party)
        db.session.commit()
        return jsonify({"id": party.id, "name": party.display_name, "document": party.document_full}), 201
    except SQLAlchemyError:
        db.session.rollback()
        return jsonify({"error": "No fue posible guardar el proveedor. Revisa que el documento no esté repetido."}), 400
    except (KeyError, TypeError, ValueError) as exc:
        db.session.rollback()
        return jsonify({"error": str(exc)}), 400


@purchases_bp.post("/inventory/locations")
@login_required
@require_role("INVENTARIO", "ADMIN")
@audit_action("CREATE_INVENTORY_LOCATION")
def create_location_route():
    payload = request.get_json(silent=True) or {}
    try:
        code = str(payload.get("code") or "").strip().upper()
        name = str(payload.get("name") or "").strip()
        location_type = str(payload.get("location_type") or "WAREHOUSE")
        if not code or not name or location_type not in ("WAREHOUSE", "PROCESSOR", "IN_TRANSIT", "CONSIGNMENT", "CUSTOMER", "SCRAP", "VIRTUAL"):
            raise ValueError("Código, nombre y tipo de ubicación son obligatorios y válidos.")
        location = InventoryLocation(code=code, name=name, location_type=location_type, notes=payload.get("notes"))
        db.session.add(location)
        db.session.commit()
        return jsonify({"id": location.id, "code": location.code, "name": location.name}), 201
    except SQLAlchemyError:
        db.session.rollback()
        return jsonify({"error": "No fue posible guardar la ubicación. Revisa que el código no esté repetido."}), 400
    except (TypeError, ValueError) as exc:
        db.session.rollback()
        return jsonify({"error": str(exc)}), 400


@purchases_bp.post("/products")
@login_required
@require_role("INVENTARIO", "COMPRAS", "ADMIN")
@audit_action("CREATE_PRODUCT")
def create_product_route():
    payload = request.get_json(silent=True) or {}
    try:
        sku = str(payload.get("sku") or "").strip().upper()
        name = str(payload.get("name") or "").strip()
        product_kind = str(payload.get("product_kind") or "RAW_MATERIAL")
        base_unit_id = int(payload["base_unit_id"])
        purchase_unit_id = int(payload.get("purchase_unit_id") or base_unit_id)
        if not sku or not name or product_kind not in PRODUCT_KINDS:
            raise ValueError("SKU, nombre y tipo de producto son obligatorios y válidos.")
        units = db.session.scalars(select(UnitOfMeasure).where(UnitOfMeasure.id.in_([base_unit_id, purchase_unit_id]), UnitOfMeasure.is_active.is_(True))).all()
        units_by_id = {unit.id: unit for unit in units}
        if len(units_by_id) != len({base_unit_id, purchase_unit_id}) or units_by_id[base_unit_id].dimension != units_by_id[purchase_unit_id].dimension:
            raise ValueError("La unidad de compra debe pertenecer a la misma dimensión que la unidad base.")
        product = Product(
            sku=sku,
            name=name,
            description=payload.get("description"),
            product_kind=product_kind,
            category_id=(int(payload["category_id"]) if payload.get("category_id") not in (None, "") else None),
            base_unit_id=base_unit_id,
            purchase_unit_id=purchase_unit_id,
            is_purchasable=bool(payload.get("is_purchasable", True)),
            is_sellable=bool(payload.get("is_sellable", False)),
            is_produced=bool(payload.get("is_produced", False)),
            tracks_batches=bool(payload.get("tracks_batches", product_kind != "SUPPLY")),
            costing_method=str(payload.get("costing_method") or "SYSTEM_DEFAULT"),
        )
        db.session.add(product)
        db.session.commit()
        return jsonify(_product_payload(product)), 201
    except SQLAlchemyError:
        db.session.rollback()
        return jsonify({"error": "No fue posible guardar el producto. Revisa SKU y relaciones."}), 400
    except (KeyError, StopIteration, TypeError, ValueError) as exc:
        db.session.rollback()
        return jsonify({"error": str(exc)}), 400


@purchases_bp.post("/units")
@login_required
@require_role("INVENTARIO", "ADMIN")
@audit_action("CREATE_UNIT")
def create_unit_route():
    payload = request.get_json(silent=True) or {}
    try:
        code = str(payload.get("code") or "").strip().upper()
        name = str(payload.get("name") or "").strip()
        dimension = str(payload.get("dimension") or "")
        if not code or not name or dimension not in ("MASS", "COUNT", "VOLUME", "TIME"):
            raise ValueError("Código, nombre y dimensión son obligatorios y válidos.")
        unit = UnitOfMeasure(code=code, name=name, dimension=dimension, decimal_places=int(payload.get("decimal_places", 3)))
        db.session.add(unit)
        db.session.commit()
        return jsonify({"id": unit.id, "code": unit.code, "name": unit.name, "dimension": unit.dimension}), 201
    except SQLAlchemyError:
        db.session.rollback()
        return jsonify({"error": "No fue posible guardar la unidad. Revisa que el código no esté repetido."}), 400
    except (TypeError, ValueError) as exc:
        db.session.rollback()
        return jsonify({"error": str(exc)}), 400


@purchases_bp.post("/units/conversions")
@login_required
@require_role("INVENTARIO", "ADMIN")
@audit_action("CREATE_UNIT_CONVERSION")
def create_unit_conversion_route():
    payload = request.get_json(silent=True) or {}
    try:
        from_unit_id = int(payload["from_unit_id"])
        to_unit_id = int(payload["to_unit_id"])
        factor = Decimal(str(payload["factor"]))
        if factor <= 0 or from_unit_id == to_unit_id:
            raise ValueError("El factor debe ser positivo y las unidades deben ser diferentes.")
        units = db.session.scalars(select(UnitOfMeasure).where(UnitOfMeasure.id.in_([from_unit_id, to_unit_id]), UnitOfMeasure.is_active.is_(True))).all()
        units_by_id = {unit.id: unit for unit in units}
        if len(units_by_id) != 2 or units_by_id[from_unit_id].dimension != units_by_id[to_unit_id].dimension:
            raise ValueError("Las unidades deben existir y compartir dimensión.")
        conversion = UnitConversion(from_unit_id=from_unit_id, to_unit_id=to_unit_id, factor=factor)
        db.session.add(conversion)
        db.session.commit()
        return jsonify({"id": conversion.id, "from_unit_id": from_unit_id, "to_unit_id": to_unit_id, "factor": str(factor)}), 201
    except SQLAlchemyError:
        db.session.rollback()
        return jsonify({"error": "No fue posible guardar la conversión. Puede que ya exista."}), 400
    except (KeyError, TypeError, ValueError) as exc:
        db.session.rollback()
        return jsonify({"error": str(exc)}), 400


@purchases_bp.get("/purchases")
@login_required
@require_role("INVENTARIO", "COMPRAS", "CONTABILIDAD", "ADMIN", "CONSULTA")
def list_purchases():
    purchases = db.session.scalars(
        select(Purchase).order_by(Purchase.purchase_date.desc(), Purchase.id.desc())
    ).all()
    return jsonify([_purchase_payload(purchase) for purchase in purchases])


@purchases_bp.post("/purchases")
@login_required
@require_role("INVENTARIO", "COMPRAS", "ADMIN")
@audit_action("CREATE_PURCHASE")
def create_purchase_route():
    payload = request.get_json(silent=True) or {}
    try:
        items_payload = payload.get("items") or []
        if not items_payload:
            raise ValueError("La compra necesita al menos una linea.")
        party = _require_supplier(int(payload["party_id"]))
        purchase_date = date.fromisoformat(payload.get("purchase_date", date.today().isoformat()))
        purchase = Purchase(
            purchase_number=str(payload.get("purchase_number") or _next_number()),
            party_id=party.id,
            purchase_type=str(payload.get("purchase_type") or "SUPPLIER"),
            purchase_date=purchase_date,
            status=str(payload.get("status") or "CONFIRMED"),
            destination_location_id=int(payload["destination_location_id"]),
            currency=str(payload.get("currency") or "COP"),
            freight_amount=Decimal(str(payload.get("freight_amount", "0"))),
            withholding_total=Decimal(str(payload.get("withholding_total", "0"))),
            supplier_document_type=payload.get("supplier_document_type"),
            supplier_document_number=payload.get("supplier_document_number"),
            notes=payload.get("notes"),
            created_by_id=current_user.id,
        )
        db.session.add(purchase)
        db.session.flush()

        subtotal = Decimal("0")
        discount_total = Decimal("0")
        tax_total = Decimal("0")
        for line_no, item_payload in enumerate(items_payload, start=1):
            product = db.session.get(Product, int(item_payload["product_id"]))
            if product is None or not product.is_active or not product.is_purchasable:
                raise ValueError("Cada linea debe referir a un producto comprable y activo.")
            unit_id = int(item_payload.get("unit_id") or product.purchase_unit_id or product.base_unit_id)
            quantity = Decimal(str(item_payload["quantity"]))
            unit_price = Decimal(str(item_payload["unit_price"]))
            discount = Decimal(str(item_payload.get("discount_amount", "0")))
            tax_rate = Decimal(str(item_payload.get("tax_rate", "0")))
            if quantity <= 0 or unit_price < 0 or discount < 0 or tax_rate < 0:
                raise ValueError("Cantidad, precio, descuento y tasa deben ser valores válidos.")
            quantity_base = convert_quantity(db.session, quantity, unit_id, product.base_unit_id, product.id)
            line_subtotal = quantity * unit_price
            line_tax = (line_subtotal - discount) * tax_rate
            item = PurchaseItem(
                line_no=line_no,
                product_id=product.id,
                quantity=quantity,
                unit_id=unit_id,
                quantity_base=quantity_base,
                unit_price=unit_price,
                discount_amount=discount,
                tax_rate=tax_rate,
                tax_amount=line_tax,
                subtotal=line_subtotal,
                total=line_subtotal - discount + line_tax,
                landed_unit_cost=Decimal("0"),
                notes=item_payload.get("notes"),
            )
            purchase.items.append(item)
            subtotal += line_subtotal
            discount_total += discount
            tax_total += line_tax

        for item in purchase.items:
            net_line = item.subtotal - item.discount_amount
            item.allocated_freight = (
                purchase.freight_amount * net_line / (subtotal - discount_total)
                if subtotal > discount_total else Decimal("0")
            )
            item.landed_unit_cost = (
                item.subtotal - item.discount_amount + item.allocated_freight
            ) / item.quantity_base
        purchase.subtotal = subtotal
        purchase.discount_total = discount_total
        purchase.tax_total = tax_total
        purchase.total = subtotal - discount_total + tax_total + purchase.freight_amount - purchase.withholding_total
        db.session.commit()
        return jsonify(_purchase_payload(purchase)), 201
    except SQLAlchemyError:
        db.session.rollback()
        return jsonify({"error": "La base de datos aún no está migrada."}), 503
    except (KeyError, TypeError, ValueError, UnitConversionError) as exc:
        db.session.rollback()
        return jsonify({"error": str(exc)}), 400


@purchases_bp.post("/purchases/<int:purchase_id>/receive")
@login_required
@require_role("INVENTARIO", "ADMIN")
@audit_action("RECEIVE_PURCHASE")
def receive_purchase_route(purchase_id: int):
    purchase = db.session.get(Purchase, purchase_id)
    if purchase is None:
        return jsonify({"error": "Compra no encontrada."}), 404
    try:
        batches = receive_purchase(
            db.session,
            purchase,
            batch_code_factory=lambda document, item: f"CP-{document.purchase_number}-{item.line_no}",
            created_by_id=current_user.id,
        )
        db.session.commit()
        return jsonify({"purchase": _purchase_payload(purchase), "batches": [batch.batch_code for batch in batches]})
    except (InventoryError, ValueError) as exc:
        db.session.rollback()
        return jsonify({"error": str(exc)}), 400


@purchases_admin_bp.get("/compras")
@login_required
@require_role("INVENTARIO", "COMPRAS", "ADMIN")
def purchases_admin_page():
    return render_template("purchases_admin.html", today=date.today().isoformat())


def _supplier_query():
    today = date.today()
    return (
        db.session.query(Party)
        .join(PartyRole, PartyRole.party_id == Party.id)
        .where(
            Party.is_active.is_(True),
            PartyRole.role_code.in_(("SUPPLIER", "COFFEE_GROWER")),
            PartyRole.valid_from <= today,
            or_(PartyRole.valid_to.is_(None), PartyRole.valid_to >= today),
        )
        .order_by(Party.legal_name)
        .distinct()
    )


def _require_supplier(party_id: int) -> Party:
    party = _supplier_query().where(Party.id == party_id).first()
    if party is None:
        raise ValueError("El tercero debe estar activo y tener rol de proveedor o caficultor.")
    return party


def _next_number() -> str:
    last_id = db.session.scalar(select(Purchase.id).order_by(Purchase.id.desc()).limit(1)) or 0
    return f"C-{int(last_id) + 1:05d}"


def _product_payload(product: Product) -> dict:
    return {
        "id": product.id,
        "sku": product.sku,
        "name": product.name,
        "base_unit_id": product.base_unit_id,
        "purchase_unit_id": product.purchase_unit_id or product.base_unit_id,
    }


def _purchase_payload(purchase: Purchase) -> dict:
    return {
        "id": purchase.id,
        "purchase_number": purchase.purchase_number,
        "party_id": purchase.party_id,
        "party_name": purchase.party.display_name if purchase.party else None,
        "purchase_date": purchase.purchase_date.isoformat(),
        "status": purchase.status,
        "destination_location_id": purchase.destination_location_id,
        "currency": purchase.currency,
        "subtotal": str(purchase.subtotal),
        "total": str(purchase.total),
        "items": [
            {"product_id": item.product_id, "quantity": str(item.quantity), "unit_price": str(item.unit_price)}
            for item in purchase.items
        ],
    }