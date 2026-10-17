"""Consultas y renderizado del directorio. Sin escrituras ni cambios de permisos."""
from datetime import date

from flask import abort, current_app, render_template, request, url_for
from sqlalchemy import exists, func, or_, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import selectinload

from app.extensions import db
from app.models.party import DOCUMENT_TYPES, Party, PartyRole

PAGE_SIZE = 20
PROFILE_LABELS = {"CUSTOMER": "Cliente", "CAFETERIA": "Cafetería", "INTERMEDIARY": "Distribuidor"}


def _filters():
    q = request.args.get("q", "").strip()[:120]
    profile = request.args.get("profile", "").strip()
    if profile not in ("", "CAFETERIA", "INTERMEDIARY"):
        abort(400, description="Perfil comercial no válido.")
    raw_page = request.args.get("page", "1")
    try:
        page = max(1, int(raw_page))
    except ValueError:
        abort(400, description="Página no válida.")
    return {"q": q, "profile": profile, "page": page}


def _role_exists(code, today):
    return exists(select(PartyRole.id).where(
        PartyRole.party_id == Party.id,
        PartyRole.role_code == code,
        PartyRole.valid_from <= today,
        or_(PartyRole.valid_to.is_(None), PartyRole.valid_to >= today),
    ))


def _directory_context(filters):
    today = date.today()
    conditions = [Party.is_active.is_(True), _role_exists("CUSTOMER", today)]
    if filters["profile"]:
        conditions.append(_role_exists(filters["profile"], today))
    if filters["q"]:
        escaped = filters["q"].replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        pattern = "%" + escaped + "%"
        conditions.append(or_(
            Party.legal_name.ilike(pattern, escape="\\"),
            Party.trade_name.ilike(pattern, escape="\\"),
            Party.document_number.ilike(pattern, escape="\\"),
            Party.email.ilike(pattern, escape="\\"),
        ))
    total = db.session.scalar(select(func.count(Party.id)).where(*conditions)) or 0
    pages = max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE)
    page = min(filters["page"], pages)
    customers = db.session.scalars(
        select(Party).where(*conditions)
        .options(selectinload(Party.party_roles))
        .order_by(Party.legal_name, Party.id)
        .offset((page - 1) * PAGE_SIZE).limit(PAGE_SIZE)
    ).all()
    profiles = {
        customer.id: [PROFILE_LABELS[code] for code in PROFILE_LABELS if code in customer.active_roles(today)]
        for customer in customers
    }
    links = {}
    for key, number in (("previous", page - 1), ("next", page + 1)):
        if 1 <= number <= pages:
            links[key] = url_for("parties_admin.customers_admin_page", q=filters["q"], profile=filters["profile"], page=number)
    return dict(customers=customers, profiles=profiles, total=total, page=page,
                pages=pages, links=links, filters=filters, directory_error=None)


def render_customers_workspace():
    """Invocar desde la ruta /clientes, conservando sus decoradores actuales."""
    filters = _filters()
    status = 200
    try:
        context = _directory_context(filters)
    except SQLAlchemyError:
        db.session.rollback()
        current_app.logger.exception("No fue posible consultar el directorio de clientes")
        status = 500
        context = dict(customers=[], profiles={}, total=0, page=1, pages=1,
                       links={}, filters=filters,
                       directory_error="No fue posible consultar los clientes. No se muestran datos de demostración.")
    partial = request.headers.get("HX-Request") == "true" and request.headers.get("HX-History-Restore-Request") != "true"
    template = "parties/_directory.html" if partial else "customers_admin.html"
    context["document_types"] = DOCUMENT_TYPES
    return render_template(template, **context), status, {
        "Cache-Control": "no-store",
        "Vary": "HX-Request, HX-History-Restore-Request",
    }
