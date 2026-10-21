"""Rutas del informe por lote. Todo es de solo lectura (SELECT)."""
from __future__ import annotations

import json
from datetime import date, datetime
from decimal import Decimal

from flask import abort, current_app, render_template, request, url_for
from flask_login import login_required
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.auth.decorators import require_role
from app.extensions import db
from app.lot_reports import analysis, lot_reports_bp
from app.lot_reports.queries import SORTS, fetch_report, list_lots

# El informe expone margenes, costos y nombres de clientes: solo finanzas y administracion.
ROLES = ("CONTABILIDAD", "ADMIN")
TYPE_LABELS = {"PRODUCED": "Producidos", "PURCHASED": "Comprados", "ADJUSTED": "Ajustados"}
STATUS_LABELS = {"ACTIVE": "Activo", "DEPLETED": "Agotado", "BLOCKED": "Bloqueado", "EXPIRED": "Vencido"}
SORT_LABELS = {
    "recent": "Más recientes",
    "revenue": "Mayor ingreso",
    "sell": "Menos vendidos primero",
    "receivable": "Mayor saldo por cobrar",
    "cost": "Mayor costo",
}
PAGE_SIZE = 12
NO_STORE = {"Cache-Control": "no-store", "Vary": "HX-Request, HX-Target, HX-History-Restore-Request"}
LIST_PARTIAL = "lot_reports/partials/_list_view.html"
RESULTS_PARTIAL = "lot_reports/partials/_results.html"
DETAIL_PARTIAL = "lot_reports/partials/_detail.html"
PAGE = "lot_reports/page.html"


@lot_reports_bp.app_template_filter("lr_money")
def lr_money(value, decimals=0):
    return analysis.money(value, decimals)


@lot_reports_bp.app_template_filter("lr_qty")
def lr_qty(value, decimals=2):
    return analysis.qty(value, decimals)


@lot_reports_bp.app_template_filter("lr_pct")
def lr_pct(value, decimals=1):
    return analysis.pct(value, decimals)


@lot_reports_bp.app_template_filter("lr_date")
def lr_date(value):
    return analysis.fdate(value)


@lot_reports_bp.app_template_filter("lr_num")
def lr_num(value):
    """Valor numerico plano (para data-count); sin formato regional."""
    return "" if value is None else format(analysis.num(value), "f")


def _execute(sql, params=None):
    return [dict(row._mapping) for row in db.session.execute(text(sql), params or {})]


def _is_htmx():
    return request.headers.get("HX-Request") == "true" and request.headers.get("HX-History-Restore-Request") != "true"


def _toast(kind, message):
    return {"HX-Trigger": json.dumps({"dn:toast": {"kind": kind, "message": message}}), "HX-Reswap": "none"}


def _filters():
    q = request.args.get("q", "").strip()[:120]
    ltype = request.args.get("type", "PRODUCED")  # por defecto: lotes producidos
    status = request.args.get("status", "")
    sort = request.args.get("sort", "recent")
    if ltype and ltype not in TYPE_LABELS:
        abort(400, description="Tipo de lote no válido.")
    if status and status not in STATUS_LABELS:
        abort(400, description="Estado de lote no válido.")
    if sort not in SORTS:
        abort(400, description="Orden no válido.")
    try:
        page = max(1, int(request.args.get("page", "1")))
    except ValueError:
        abort(400, description="Página no válida.")
    return {"q": q, "type": ltype, "status": status, "sort": sort, "page": page}


def _cutoff():
    raw = request.args.get("corte", "").strip()
    if not raw:
        return date.today()
    try:
        return date.fromisoformat(raw)
    except ValueError:
        abort(400, description="Fecha de corte no válida (AAAA-MM-DD).")


def _page_links(filters, page, pages):
    links = {}
    for name, number in (("previous", page - 1), ("next", page + 1)):
        if 1 <= number <= pages:
            links[name] = url_for("lot_reports.index", q=filters["q"], type=filters["type"], status=filters["status"],
                                  sort=filters["sort"], page=number)
    return links


def _labels():
    return {"type_labels": TYPE_LABELS, "status_labels": STATUS_LABELS, "sort_labels": SORT_LABELS}


def _list_context(filters):
    data = list_lots(_execute, filters, PAGE_SIZE)
    ints = ("lots", "with_sales", "active")
    return {"filters": filters, "list_error": False, "partial": _is_htmx(),
            "summary": {k: int(v or 0) if k in ints else analysis.num(v) for k, v in data["summary"].items()},
            "lots": [analysis.enrich_lot_row(r) for r in data["rows"]], "page": data["page"], "pages": data["pages"],
            "links": _page_links(filters, data["page"], data["pages"]), "type_counts": data["type_counts"], **_labels()}


def _empty_list(filters):
    return {"filters": filters, "list_error": True, "partial": False, "page": 1, "pages": 1, "links": {}, "type_counts": {},
            "summary": {"lots": 0, "with_sales": 0, "active": 0, "lot_cost": 0, "revenue": 0, "cogs": 0, "receivable": 0},
            "lots": [], **_labels()}


@lot_reports_bp.get("/reportes/lotes")
@login_required
@require_role(*ROLES)
def index():
    filters = _filters()
    try:
        context = _list_context(filters)
    except SQLAlchemyError:
        db.session.rollback()
        current_app.logger.exception("No fue posible consultar los lotes")
        if _is_htmx():
            return "", 200, {**NO_STORE, **_toast("error", "No fue posible consultar los lotes.")}
        return render_template(PAGE, stage_template=LIST_PARTIAL, page_title="Informe por lote", **_empty_list(filters)), 500, NO_STORE
    if _is_htmx() and request.headers.get("HX-Target") == "lots-results":
        return render_template(RESULTS_PARTIAL, **context), 200, NO_STORE
    if _is_htmx():
        return render_template(LIST_PARTIAL, **context), 200, NO_STORE
    return render_template(PAGE, stage_template=LIST_PARTIAL, page_title="Informe por lote", **context), 200, NO_STORE


def _load(code):
    if not code or len(code) > 40:
        abort(404)
    data = fetch_report(_execute, code)
    return data if data["identidad"] else None


@lot_reports_bp.get("/reportes/lotes/<code>")
@login_required
@require_role(*ROLES)
def detail(code):
    cutoff = _cutoff()
    try:
        data = _load(code)
    except SQLAlchemyError:
        db.session.rollback()
        current_app.logger.exception("No fue posible construir el informe del lote %s", code)
        if _is_htmx():
            return "", 200, {**NO_STORE, **_toast("error", "No fue posible generar el informe de este lote.")}
        abort(500)
    if data is None:
        if _is_htmx():
            return "", 200, {**NO_STORE, **_toast("error", f"El lote {code} no existe.")}
        abort(404)
    report = analysis.build_report(data, cutoff)
    if _is_htmx():
        return render_template(DETAIL_PARTIAL, report=report, code=code, partial=True), 200, NO_STORE
    return render_template(PAGE, stage_template=DETAIL_PARTIAL, report=report, code=code, partial=False,
                           page_title=f"Informe {code}"), 200, NO_STORE


class _Encoder(json.JSONEncoder):
    def default(self, o):
        if isinstance(o, Decimal):
            return float(o)
        if isinstance(o, (date, datetime)):
            return o.isoformat()
        return str(o)


@lot_reports_bp.get("/reportes/lotes/<code>/datos.json")
@login_required
@require_role(*ROLES)
def snapshot(code):
    """Foto de los datos del informe; sirve con `informe_lote.py --from-json` para reconstruirlo fuera del ERP."""
    cutoff = _cutoff()
    data = _load(code)
    if data is None:
        abort(404)
    data["meta"] = {"batch_code": code, "cutoff": cutoff.isoformat(), "source": "ERP (módulo de reportes)",
                    "generated_at": datetime.now().isoformat(timespec="seconds")}
    body = json.dumps(data, ensure_ascii=False, indent=1, cls=_Encoder)
    safe = "".join(ch if ch.isalnum() or ch in "-_." else "_" for ch in code)
    return body, 200, {**NO_STORE, "Content-Type": "application/json; charset=utf-8",
                       "Content-Disposition": f'attachment; filename="informe_{safe}.json"'}
