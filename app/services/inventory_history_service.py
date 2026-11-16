"""Historial de consulta. No crea ni modifica inventario."""
from collections import defaultdict
from datetime import date, datetime, time, timedelta, timezone

from flask import abort, request, url_for
from sqlalchemy import and_, case, func, or_, select
from sqlalchemy.orm import joinedload, selectinload

from app.extensions import db
from app.models.inventory import InventoryBalance, InventoryLocation, InventoryMovement
from app.models.product import Product
from app.models.batch import Batch
from app.models.shipment import Shipment, ShipmentItem
from app.models.sale import Sale, SaleItem, SaleItemBatch

TZ = timezone(timedelta(hours=-5), "America/Bogota")
LABELS = {
    "IN_PURCHASE": "Compra", "IN_PRODUCTION": "Ingreso de producción",
    "OUT_PRODUCTION": "Consumo de producción", "IN_SALE_RETURN": "Devolución de venta",
    "OUT_SALE": "Venta", "IN_ADJUSTMENT": "Ajuste de entrada",
    "OUT_ADJUSTMENT": "Ajuste de salida", "IN_TRANSFER": "Entrada por traslado",
    "OUT_TRANSFER": "Salida por traslado", "IN_WASTE_RECOVERY": "Recuperación",
    "OUT_WASTE": "Merma", "OUT_SAMPLE": "Muestra / obsequio",
    "OUT_PURCHASE_RETURN": "Devolución de compra",
}
CATEGORIES = {
    "": "Todas las operaciones", "sales": "Ventas", "transfers": "Traslados",
    "production": "Producción", "adjustments": "Ajustes", "returns": "Devoluciones",
    "purchases": "Compras", "other": "Mermas, muestras y recuperación",
}
TYPES = {
    "sales": ("OUT_SALE",), "transfers": ("IN_TRANSFER", "OUT_TRANSFER"),
    "production": ("IN_PRODUCTION", "OUT_PRODUCTION"),
    "adjustments": ("IN_ADJUSTMENT", "OUT_ADJUSTMENT"),
    "returns": ("IN_SALE_RETURN", "OUT_PURCHASE_RETURN"),
    "purchases": ("IN_PURCHASE",),
    "other": ("OUT_WASTE", "OUT_SAMPLE", "IN_WASTE_RECOVERY"),
}
STATUSES = {"PENDING": "Pendiente", "DISPATCHED": "En tránsito",
            "IN_TRANSIT": "En tránsito", "DELIVERED": "Recibido",
            "FAILED": "Entrega fallida", "RETURNED": "Devuelto", "CANCELLED": "Cancelado"}


def local_datetime(value):
    if value is None:
        return "—"
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(TZ).strftime("%d/%m/%Y %H:%M")


def presentation(product):
    profile = product.coffee_profile
    if profile is None:
        return "Presentación no registrada"
    grind = {"GRANO": "En grano", "GRUESO": "Molido grueso", "MEDIO": "Molido medio",
             "FINO": "Molido fino", "EXPRESO": "Molido expreso"}.get(profile.grind_type)
    parts = []
    if profile.packaging_grams:
        grams = format(profile.packaging_grams, "f")
        if "." in grams:
            grams = grams.rstrip("0").rstrip(".")
        parts.append(grams + " g")
    if grind:
        parts.append(grind)
    return " · ".join(parts) or "Presentación no registrada"


def unit_totals(items):
    totals = defaultdict(lambda: 0)
    for item in items:
        totals[item.unit.code] += item.quantity
    return sorted(totals.items())


def shipment_options():
    return (
        joinedload(Shipment.origin_location), joinedload(Shipment.destination_location),
        selectinload(Shipment.items).joinedload(ShipmentItem.product).joinedload(Product.coffee_profile),
        selectinload(Shipment.items).joinedload(ShipmentItem.batch),
        selectinload(Shipment.items).joinedload(ShipmentItem.unit),
    )


def _integer(name):
    raw = request.args.get(name, "").strip()
    if not raw:
        return None
    try:
        value = int(raw)
    except ValueError:
        abort(400, description="Filtro numérico no válido: " + name)
    if value < 1:
        abort(400, description="Filtro numérico fuera de rango: " + name)
    return value


def _filters(product_id):
    f = {"location": _integer("location"), "batch": _integer("batch"),
         "page": _integer("history_page") or 1,
         "category": request.args.get("category", ""),
         "flow": request.args.get("flow", ""),
         "start": request.args.get("start", ""), "end": request.args.get("end", "")}
    if f["category"] not in CATEGORIES or f["flow"] not in ("", "in", "out"):
        abort(400, description="Tipo de operación o sentido no válido.")
    if f["location"] and db.session.get(InventoryLocation, f["location"]) is None:
        abort(400, description="La ubicación no existe.")
    for name in ("start", "end"):
        try:
            f[name + "_date"] = date.fromisoformat(f[name]) if f[name] else None
            if f[name + "_date"] and not 1900 <= f[name + "_date"].year <= 9998:
                raise ValueError()
        except ValueError:
            abort(400, description="Fecha no válida.")
    if f["start_date"] and f["end_date"] and f["start_date"] > f["end_date"]:
        abort(400, description="La fecha inicial no puede superar la final.")
    if f["batch"]:
        found = db.session.scalar(select(InventoryMovement.id).where(
            InventoryMovement.product_id == product_id, InventoryMovement.batch_id == f["batch"]).limit(1))
        if found is None:
            abort(400, description="El lote no tiene movimientos para este producto.")
    return f


def history_context(product):
    f = _filters(product.id)
    M = InventoryMovement
    valid_transfer = and_(Shipment.id.is_not(None), M.reverses_movement_id.is_(None))
    join_clause = and_(M.reference_type == "TRANSFER", M.reference_id == Shipment.id,
                      Shipment.shipment_type == "TRANSFER",
                      M.movement_type.in_(TYPES["transfers"]))
    group_kind = case((valid_transfer, "transfer"), else_="movement")
    group_id = case((valid_transfer, M.reference_id), else_=M.id)
    conditions = [M.product_id == product.id]
    if f["batch"]:
        conditions.append(M.batch_id == f["batch"])
    if f["category"]:
        conditions.append(M.movement_type.in_(TYPES[f["category"]]))
    if f["start_date"]:
        conditions.append(M.occurred_at >= datetime.combine(f["start_date"], time.min, TZ).astimezone(timezone.utc))
    if f["end_date"]:
        conditions.append(M.occurred_at < datetime.combine(f["end_date"] + timedelta(days=1), time.min, TZ).astimezone(timezone.utc))
    if f["location"]:
        loc = f["location"]
        transfer_side = (Shipment.destination_location_id == loc if f["flow"] == "in" else
                         Shipment.origin_location_id == loc if f["flow"] == "out" else
                         or_(Shipment.origin_location_id == loc, Shipment.destination_location_id == loc, M.location_id == loc))
        ordinary = M.location_id == loc
        if f["flow"]:
            ordinary = and_(ordinary, M.direction == (1 if f["flow"] == "in" else -1))
        location = db.session.get(InventoryLocation, loc)
        if location.location_type == "IN_TRANSIT" and f["flow"]:
            transfer_side = ordinary
        conditions.append(or_(and_(valid_transfer, transfer_side), and_(~valid_transfer, ordinary)))
    elif f["flow"]:
        conditions.append(or_(valid_transfer, M.direction == (1 if f["flow"] == "in" else -1)))
    matching = select(group_kind.label("kind"), group_id.label("key"), M.occurred_at.label("at"),
                      M.id.label("movement_id")).outerjoin(Shipment, join_clause).where(*conditions).subquery()
    grouped = select(matching.c.kind, matching.c.key, func.max(matching.c.at).label("last_at"),
                     func.max(matching.c.movement_id).label("last_id")).group_by(matching.c.kind, matching.c.key).subquery()
    total = db.session.scalar(select(func.count()).select_from(grouped)) or 0
    pages = max(1, (total + 19) // 20)
    page = min(f["page"], pages)
    keys = db.session.execute(select(grouped).order_by(grouped.c.last_at.desc(), grouped.c.last_id.desc(),
        grouped.c.kind, grouped.c.key).offset((page - 1) * 20).limit(20)).mappings().all()
    transfer_ids = [r["key"] for r in keys if r["kind"] == "transfer"]
    movement_ids = [r["key"] for r in keys if r["kind"] == "movement"]
    shipments = {s.id: s for s in db.session.scalars(select(Shipment).where(
        Shipment.id.in_(transfer_ids)).options(*shipment_options())).all()} if transfer_ids else {}
    movement_conditions = [M.product_id == product.id]
    if f["batch"]:
        movement_conditions.append(M.batch_id == f["batch"])
    movement_conditions.append(or_(M.id.in_(movement_ids), and_(M.reference_type == "TRANSFER",
        M.reference_id.in_(transfer_ids), M.movement_type.in_(TYPES["transfers"]), M.reverses_movement_id.is_(None))))
    movements = db.session.scalars(select(M).where(*movement_conditions).options(
        joinedload(M.location), joinedload(M.unit), joinedload(M.batch)).order_by(M.occurred_at, M.id)).all() if keys else []
    by_id = {m.id: m for m in movements}
    transfer_moves = defaultdict(list)
    for m in movements:
        if m.id not in movement_ids and m.reference_type == "TRANSFER":
            transfer_moves[m.reference_id].append(m)
    sale_refs = {m.reference_id for m in movements if m.reference_type == "SALE_ITEM_BATCH"}
    sales = {a.id: a for a in db.session.scalars(select(SaleItemBatch).where(SaleItemBatch.id.in_(sale_refs)).options(
        joinedload(SaleItemBatch.sale_item).joinedload(SaleItem.sale).joinedload(Sale.party))).all()} if sale_refs else {}
    operations = []
    for row in keys:
        if row["kind"] == "transfer":
            s = shipments[row["key"]]
            items = [i for i in s.items if i.product_id == product.id and (not f["batch"] or i.batch_id == f["batch"])]
            operations.append({"kind": "transfer", "shipment": s, "items": items,
                "totals": unit_totals(items), "movements": transfer_moves[s.id],
                "at": row["last_at"], "status": STATUSES.get(s.status, s.status)})
        else:
            m = by_id[row["key"]]
            allocation = sales.get(m.reference_id) if m.reference_type == "SALE_ITEM_BATCH" else None
            operations.append({"kind": "movement", "movement": m, "at": row["last_at"],
                "label": LABELS.get(m.movement_type, m.movement_type),
                "sale": allocation.sale_item.sale if allocation else None,
                "description": allocation.sale_item.description if allocation else None})
    balance_conditions = [InventoryBalance.product_id == product.id, InventoryBalance.quantity_base != 0]
    if f["location"]:
        balance_conditions.append(InventoryBalance.location_id == f["location"])
    if f["batch"]:
        balance_conditions.append(InventoryBalance.batch_id == f["batch"])
    balances = db.session.scalars(select(InventoryBalance).where(*balance_conditions).options(
        joinedload(InventoryBalance.location), joinedload(InventoryBalance.batch)).order_by(
        InventoryBalance.location_id, InventoryBalance.batch_id)).all()
    locations = db.session.scalars(select(InventoryLocation).order_by(InventoryLocation.name)).all()
    batches = db.session.scalars(select(Batch).where(Batch.id.in_(select(M.batch_id).where(
        M.product_id == product.id, M.batch_id.is_not(None)))).order_by(Batch.batch_code)).all()
    params = {k: f[k] or "" for k in ("location", "batch", "category", "flow", "start", "end")}
    links = {name: url_for("inventory_admin.product_detail", product_id=product.id,
        history_page=n, **params) for name, n in (("previous", page - 1), ("next", page + 1)) if 1 <= n <= pages}
    return {"product": product, "balances": balances, "operations": operations, "history_filters": f,
        "history_locations": locations, "history_batches": batches, "categories": CATEGORIES,
        "history_total": total, "history_page": page, "history_pages": pages,
        "history_links": links, "today": datetime.now(TZ).date(),
        "history_partial": request.headers.get("HX-Request") == "true"}
