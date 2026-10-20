"""Elegir bodegas de despacho según el inventario real."""
from __future__ import annotations

from decimal import Decimal

from flask import current_app
from sqlalchemy import func, select
from sqlalchemy.orm import joinedload

from app.extensions import db
from app.models.inventory import InventoryBalance, InventoryLocation
from app.models.product import Product
from app.services.units import UnitConversionError, convert_quantity

from app.services.shipping_service import find_city, get_city

def origin_dane_code(location: InventoryLocation) -> str | None:
    overrides = current_app.config.get("STOREFRONT_LOCATION_DANE", {})
    if location.code in overrides:
        return overrides[location.code]

    addr = location.address
    if addr is None:
        return None

    muni = (addr.municipality_code or "").strip()
    if len(muni) == 5 and muni.isdigit():
        code = f"{muni}000"
        if get_city(code):
            return code

    city = find_city(addr.municipality_name, addr.department_name)
    return city["codigo"] if city else None

def _base_per_sale_unit(product: Product) -> Decimal | None:
    if product.effective_sales_unit_id == product.base_unit_id:
        return Decimal(1)
    try:
        factor = convert_quantity(
            db.session, Decimal(1), product.effective_sales_unit_id,
            product.base_unit_id, product.id,
        )
    except UnitConversionError:
        return None
    return factor if factor > 0 else None


def candidate_origins(cart: dict) -> list[tuple[InventoryLocation, str]]:
    """Bodegas que cubren el pedido completo, con su código DANE."""
    wanted = {i["product_id"]: i["quantity"] for i in cart["items"]}
    loc_ids = tuple(
        int(x) for x in current_app.config.get("STOREFRONT_STOCK_LOCATION_IDS", ())
    )
    
    if not wanted or not loc_ids:
        return []

    products = db.session.scalars(
        select(Product).where(Product.id.in_(wanted))
    ).all()
    factors = {p.id: _base_per_sale_unit(p) for p in products}
    if len(factors) != len(wanted) or any(f is None for f in factors.values()):
        return []

    rows = db.session.execute(
        select(
            InventoryBalance.location_id,
            InventoryBalance.product_id,
            func.sum(InventoryBalance.quantity_base),
        )
        .where(
            InventoryBalance.product_id.in_(wanted),
            InventoryBalance.location_id.in_(loc_ids),
            InventoryBalance.quantity_base > 0,
        )
        .group_by(InventoryBalance.location_id, InventoryBalance.product_id)
    ).all()

    stock: dict[int, dict[int, Decimal]] = {}
    for loc_id, pid, qty in rows:
        stock.setdefault(loc_id, {})[pid] = Decimal(str(qty))

    ok_ids = [
        loc_id for loc_id, per in stock.items()
        if all(
            per.get(pid, Decimal(0)) // factors[pid] >= qty
            for pid, qty in wanted.items()
        )
    ]
    if not ok_ids:
        return []

    locations = db.session.scalars(
        select(InventoryLocation)
        .options(joinedload(InventoryLocation.address))
        .where(
            InventoryLocation.id.in_(ok_ids),
            InventoryLocation.location_type == "WAREHOUSE",
            InventoryLocation.is_active.is_(True),
        )
        .order_by(InventoryLocation.name)
    ).all()

    result = []
    for loc in locations:
        dane = origin_dane_code(loc)
        if dane:
            result.append((loc, dane))
    return result


def explain_origins(cart: dict) -> list[dict]:
    wanted = {i["product_id"]: i["quantity"] for i in cart["items"]}
    loc_ids = tuple(
        int(x) for x in current_app.config.get("STOREFRONT_STOCK_LOCATION_IDS", ())
    )
    if not wanted or not loc_ids:
        return []

    rows = db.session.execute(
        select(
            InventoryBalance.location_id,
            InventoryBalance.product_id,
            func.sum(InventoryBalance.quantity_base),
        )
        .where(
            InventoryBalance.product_id.in_(wanted),
            InventoryBalance.location_id.in_(loc_ids),
        )
        .group_by(InventoryBalance.location_id, InventoryBalance.product_id)
    ).all()
    stock: dict[int, dict[int, Decimal]] = {}
    for loc_id, pid, qty in rows:
        stock.setdefault(loc_id, {})[pid] = Decimal(str(qty))

    locations = db.session.scalars(
        select(InventoryLocation)
        .options(joinedload(InventoryLocation.address))
        .where(InventoryLocation.id.in_(loc_ids))
    ).all()

    report = []
    for loc in locations:
        per = stock.get(loc.id, {})
        report.append({
            "code": loc.code,
            "type": loc.location_type,
            "active": loc.is_active,
            "dane": origin_dane_code(loc),
            "stock": {pid: str(per.get(pid, 0)) for pid in wanted},
            "covers": all(per.get(pid, Decimal(0)) >= q for pid, q in wanted.items()),
        })
    return report