from datetime import date
from decimal import Decimal
from urllib.parse import urlsplit

from flask import abort, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

import json

from sqlalchemy import case, exists, func, or_, select
from sqlalchemy.orm import joinedload

from app.auth.decorators import require_role
from app.extensions import db
from app.inventory import inventory_admin_bp
from app.models.batch import Batch
from app.models.inventory import InventoryBalance, InventoryLocation, InventoryMovement
from app.models.product import Product
from app.services.catalog_service import PUBLIC_COFFEES

from app.models.shipment import Shipment
from app.services.inventory_service import InventoryError
from app.services.transfer_service import dispatch_transfer, receive_transfer

from time import perf_counter

PHYSICAL_TYPES = ("WAREHOUSE", "PROCESSOR", "CONSIGNMENT", "IN_TRANSIT")
KIND_LABELS = {
    "FINISHED": "Café terminado",
    "RAW_MATERIAL": "Materia prima",
    "SEMI_FINISHED": "Semielaborado",
    "SUPPLY": "Empaques e insumos",
}
ROLES = ("INVENTARIO", "COMPRAS", "CONTABILIDAD", "ADMIN", "CONSULTA")


def _image(product):
    path = (product.image_path or "").strip()
    source = "Foto del producto"
    if not path:
        for definition in PUBLIC_COFFEES.values():
            if product.id in definition.product_ids:
                path = definition.hero_image
                source = "Foto del catálogo de esta referencia"
                break
    if not path:
        return None, None
    parsed = urlsplit(path)
    if parsed.scheme:
        return (path, source) if parsed.scheme in ("http", "https") and parsed.netloc else (None, None)
    if path.startswith("//"):
        return None, None
    path = path.replace("\\", "/").lstrip("/")
    if path.startswith("static/"):
        path = path[len("static/"):]
    if path.startswith("app/static/"):
        path = path[len("app/static/"):]
    if not path or ".." in path.split("/"):
        return None, None
    return url_for("static", filename=path), source


def _location_clause(location_id):
    if location_id:
        return InventoryBalance.location_id == location_id
    return InventoryLocation.location_type.in_(PHYSICAL_TYPES)


def _filters():
    q = request.args.get("q", "").strip()[:120]
    kind = request.args.get("kind", "")
    stock = request.args.get("stock", "")
    location_raw = request.args.get("location", "").strip()
    if kind and kind not in KIND_LABELS:
        abort(400, description="Tipo de producto no válido.")
    if stock not in ("", "positive", "empty", "low", "negative"):
        abort(400, description="Filtro de existencia no válido.")
    try:
        location_id = int(location_raw) if location_raw else None
        page = max(1, int(request.args.get("page", "1")))
    except ValueError:
        abort(400, description="Ubicación o página no válida.")
    if location_id is not None and db.session.get(InventoryLocation, location_id) is None:
        abort(400, description="La ubicación no existe.")
    return {"q": q, "kind": kind, "stock": stock,
            "location": location_id, "page": page}


def _listing(filters):
    totals = (
        select(
            InventoryBalance.product_id.label("product_id"),
            func.sum(InventoryBalance.quantity_base).label("quantity"),
            func.count(func.distinct(case(
                (InventoryBalance.quantity_base > 0, InventoryBalance.batch_id)
            ))).label("lots"),
            func.count(func.distinct(case(
                (InventoryBalance.quantity_base != 0, InventoryBalance.location_id)
            ))).label("locations"),
            func.max(case((InventoryBalance.quantity_base < 0, 1), else_=0)).label("negative"),
        )
        .join(InventoryLocation, InventoryLocation.id == InventoryBalance.location_id)
        .where(_location_clause(filters["location"]))
        .group_by(InventoryBalance.product_id)
        .subquery()
    )
    quantity = func.coalesce(totals.c.quantity, 0)
    negative = func.coalesce(totals.c.negative, 0)
    conditions = [Product.product_kind != "SERVICE", or_(Product.is_active.is_(True), totals.c.product_id.is_not(None))]
    if filters["kind"]:
        conditions.append(Product.product_kind == filters["kind"])
    if filters["q"]:
        pattern = "%" + filters["q"].replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
        lot_match = exists(
            select(InventoryBalance.id)
            .join(Batch, Batch.id == InventoryBalance.batch_id)
            .join(InventoryLocation, InventoryLocation.id == InventoryBalance.location_id)
            .where(InventoryBalance.product_id == Product.id,
                   _location_clause(filters["location"]),
                   Batch.batch_code.ilike(pattern, escape="\\"))
        )
        conditions.append(or_(Product.name.ilike(pattern, escape="\\"),
                              Product.sku.ilike(pattern, escape="\\"), lot_match))
    low = (quantity > 0) & Product.min_stock.is_not(None) & (quantity <= Product.min_stock)
    stock = filters["stock"]
    if stock == "positive": conditions.append(quantity > 0)
    elif stock == "empty": conditions.append(quantity == 0)
    elif stock == "low": conditions.append(low)
    elif stock == "negative": conditions.append(negative > 0)

    summary_stmt = select(
        func.count(Product.id),
        func.coalesce(func.sum(case((quantity > 0, 1), else_=0)), 0),
        func.coalesce(func.sum(case((quantity == 0, 1), else_=0)), 0),
        func.coalesce(func.sum(case((low, 1), else_=0)), 0),
        func.coalesce(func.sum(case((negative > 0, 1), else_=0)), 0),
    ).outerjoin(totals, totals.c.product_id == Product.id).where(*conditions)
    
    summary_started = perf_counter()

    total, positive, empty, low_count, negative_count = (
        db.session.execute(summary_stmt).one()
    )

    summary_ms = (perf_counter() - summary_started) * 1000

    page_size = 12
    pages = max(1, (total + page_size - 1) // page_size)
    page = min(filters["page"], pages)
    rows_started = perf_counter()
    rows = db.session.execute(
        select(Product, quantity, totals.c.lots, totals.c.locations, negative)
        .outerjoin(totals, totals.c.product_id == Product.id)
        .where(*conditions)
        .options(joinedload(Product.base_unit), joinedload(Product.category))
        .order_by(Product.name, Product.id)
        .offset((page - 1) * page_size).limit(page_size)
    ).all()
    cards = []
    rows_ms = (perf_counter() - rows_started) * 1000
    cards_started = perf_counter()
    for product, value, lots, locations, has_negative in rows:
        value = Decimal(value)
        status, label = "ok", "Con existencia"
        if has_negative: status, label = "negative", "Revisar saldo negativo"
        elif value == 0: status, label = "empty", "Sin existencia"
        elif product.min_stock is not None and value <= product.min_stock:
            status, label = "low", "Bajo mínimo"
        image, image_label = _image(product)
        cards.append({"product": product, "quantity": value, "lots": lots or 0,
                      "locations": locations or 0, "status": status, "label": label,
                      "image": image, "image_label": image_label,
                      "kind_label": KIND_LABELS.get(product.product_kind, product.product_kind)})
    cards_ms = (perf_counter() - cards_started) * 1000
    links = {}
    for name, number in (("previous", page - 1), ("next", page + 1)):
        if 1 <= number <= pages:
            links[name] = url_for("inventory_admin.workspace", q=filters["q"], kind=filters["kind"],
                                  stock=stock, location=filters["location"] or "", page=number)
    return {"_timings": {
                "summary_query": summary_ms,
                "cards_query": rows_ms,
                "cards_build": cards_ms,
            },
            "cards": cards, "summary": {"total": total, "positive": positive,
            "empty": empty, "low": low_count, "negative": negative_count},
            "page": page, "pages": pages, "links": links, "filters": filters}


@inventory_admin_bp.app_template_filter("inventory_quantity")
def inventory_quantity(value):
    result = f"{Decimal(value):,.4f}".rstrip("0").rstrip(".")
    return result.replace(",", "_").replace(".", ",").replace("_", ".")


@inventory_admin_bp.get("/inventario")
@login_required
@require_role(*ROLES)
def workspace():
    started = perf_counter()

    filters = _filters()
    filters_finished = perf_counter()

    context = _listing(filters)
    listing_finished = perf_counter()

    is_partial = (
        request.headers.get("HX-Request") == "true"
        and request.headers.get("HX-History-Restore-Request") != "true"
    )

    if is_partial:
        template = "inventory/partials/_results.html"
    else:
        template = "inventory/index.html"
        context["locations"] = db.session.scalars(
            select(InventoryLocation)
            .order_by(InventoryLocation.name)
        ).all()
        context["kinds"] = KIND_LABELS

    context_finished = perf_counter()

    html = render_template(template, **context)
    render_finished = perf_counter()

    filters_ms = (filters_finished - started) * 1000
    listing_ms = (listing_finished - filters_finished) * 1000
    context_ms = (context_finished - listing_finished) * 1000
    render_ms = (render_finished - context_finished) * 1000
    route_ms = (render_finished - started) * 1000

    listing_timings = context.pop("_timings", {})

    server_timing = ", ".join([
        f"filters;dur={filters_ms:.1f}",
        f"listing;dur={listing_ms:.1f}",
        f"context;dur={context_ms:.1f}",
        f"render;dur={render_ms:.1f}",
        f"route;dur={route_ms:.1f}",
    ])

    for name, duration in listing_timings.items():
        server_timing += f", {name};dur={duration:.1f}"

    return html, 200, {
        "Cache-Control": "no-store",
        "Vary": "HX-Request, HX-History-Restore-Request",
        "Server-Timing": server_timing,
    }


@inventory_admin_bp.get("/inventario/productos/<int:product_id>")
@login_required
@require_role(*ROLES)
def product_detail(product_id):
    product = db.session.get(Product, product_id)
    if product is None or product.product_kind == "SERVICE":
        abort(404)
    balances = db.session.scalars(
        select(InventoryBalance)
        .where(InventoryBalance.product_id == product.id, InventoryBalance.quantity_base != 0)
        .options(joinedload(InventoryBalance.location), joinedload(InventoryBalance.batch))
        .order_by(InventoryBalance.location_id, InventoryBalance.batch_id)
    ).all()
    movements = db.session.scalars(
        select(InventoryMovement).where(InventoryMovement.product_id == product.id)
        .options(joinedload(InventoryMovement.location), joinedload(InventoryMovement.batch), joinedload(InventoryMovement.unit))
        .order_by(InventoryMovement.occurred_at.desc(), InventoryMovement.id.desc()).limit(20)
    ).all()
    context = {"product": product, "balances": balances, "movements": movements, "today": date.today()}
    partial = request.headers.get("HX-Request") == "true"
    return render_template("inventory/partials/_detail.html" if partial else "inventory/detail.html",
                           **context), 200, {"Cache-Control": "no-store", "Vary": "HX-Request"}


TRANSFER_ROLES = ("INVENTARIO", "ADMIN")





@inventory_admin_bp.get("/inventario/traslados/existencias")
@login_required
@require_role(*TRANSFER_ROLES)
def transfer_stock():
    from_id = request.args.get("from_location_id", type=int)
    balances = []
    if from_id:
        balances = db.session.scalars(
            select(InventoryBalance)
            .where(InventoryBalance.location_id == from_id,
                   InventoryBalance.quantity_base > 0)
            .options(joinedload(InventoryBalance.product),
                     joinedload(InventoryBalance.batch))
            .order_by(InventoryBalance.product_id, InventoryBalance.batch_id)
        ).all()
    return render_template("inventory/partials/_transfer_stock.html",
                           balances=balances)



def _is_htmx() -> bool:
    return request.headers.get("HX-Request") == "true"


def _recent_transfers():
    return db.session.scalars(
        select(Shipment)
        .where(Shipment.shipment_type == "TRANSFER")
        .options(joinedload(Shipment.origin_location),
                 joinedload(Shipment.destination_location),
                 joinedload(Shipment.items))
        .order_by(Shipment.id.desc()).limit(30)
    ).unique().all()


def _board(flash_id=None):
    return render_template("inventory/partials/_transfer_board.html",
                           shipments=_recent_transfers(), flash_id=flash_id)


def _hx(kind: str, message: str, **events):
    payload = {"dn:toast": {"kind": kind, "message": message}, **events}
    return {"HX-Trigger": json.dumps(payload)}


def _error_message(exc: Exception) -> str:
    if isinstance(exc, InventoryError):
        return str(exc)
    return "Revisa las cantidades y los datos del traslado."


@inventory_admin_bp.get("/inventario/traslados")
@login_required
@require_role(*TRANSFER_ROLES)
def transfers():
    warehouses = db.session.scalars(
        select(InventoryLocation)
        .where(InventoryLocation.location_type == "WAREHOUSE",
               InventoryLocation.is_active.is_(True))
        .order_by(InventoryLocation.name)
    ).all()
    return render_template("inventory/transfers.html", warehouses=warehouses,
                           shipments=_recent_transfers(), flash_id=None), 200, {
        "Cache-Control": "no-store",
    }


@inventory_admin_bp.post("/inventario/traslados")
@login_required
@require_role(*TRANSFER_ROLES)
def transfer_create():
    try:
        from_id = int(request.form["from_location_id"])
        to_id = int(request.form["to_location_id"])
        lines = []
        for key, raw in request.form.items():
            if not key.startswith("qty_") or not raw.strip():
                continue
            qty = Decimal(raw.replace(",", "."))
            if qty <= 0:
                continue
            balance = db.session.get(InventoryBalance, int(key[4:]))
            if balance is None or balance.location_id != from_id:
                raise InventoryError("Una línea no pertenece a la bodega origen.")
            lines.append({"product_id": balance.product_id,
                          "batch_id": balance.batch_id, "quantity": qty})

        shipment = dispatch_transfer(
            db.session, from_location_id=from_id, to_location_id=to_id,
            lines=lines,
            carrier_name=request.form.get("carrier_name", "").strip() or None,
            tracking_number=request.form.get("tracking_number", "").strip() or None,
            freight_cost=Decimal(
                (request.form.get("freight_cost") or "0").replace(",", ".")
            ),
            user_id=current_user.id,
            notes=request.form.get("notes", "").strip() or None,
        )
        db.session.commit()
    except (KeyError, ValueError, ArithmeticError, InventoryError) as exc:
        db.session.rollback()
        message = _error_message(exc)
        if _is_htmx():
            return "", 200, {**_hx("error", message), "HX-Reswap": "none"}
        flash(message, "error")
        return redirect(url_for("inventory_admin.transfers"))

    message = f"Traslado {shipment.shipment_number} despachado."
    if _is_htmx():
        return _board(shipment.id), 200, _hx(
            "success", message, **{"dn:dispatched": {"id": shipment.id}})
    flash(message, "success")
    return redirect(url_for("inventory_admin.transfers"))


@inventory_admin_bp.post("/inventario/traslados/<int:shipment_id>/recibir")
@login_required
@require_role(*TRANSFER_ROLES)
def transfer_receive(shipment_id: int):
    try:
        shipment = receive_transfer(
            db.session, shipment_id, user_id=current_user.id,
            received_by=str(current_user.get_id()),
        )
        db.session.commit()
    except InventoryError as exc:
        db.session.rollback()
        if _is_htmx():
            return "", 200, {**_hx("error", str(exc)), "HX-Reswap": "none"}
        flash(str(exc), "error")
        return redirect(url_for("inventory_admin.transfers"))

    message = f"Traslado {shipment.shipment_number} recibido."
    if _is_htmx():
        return _board(shipment.id), 200, _hx("success", message)
    flash(message, "success")
    return redirect(url_for("inventory_admin.transfers"))
