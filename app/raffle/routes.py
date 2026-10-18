"""Sorteo publico. Los participantes se guardan como clientes (parties); no hay tablas de sorteo."""
from __future__ import annotations

from datetime import date, datetime, timezone

from flask import current_app, render_template, request
from flask_login import login_required
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from app.extensions import db
from app.models.party import Party, PartyRole
from app.raffle import raffle_bp
from app.raffle.participation import (
    BOGOTA, append_note, build_line, has_participation, new_entry_code,
    parse_participation, provisional_document, tag,
)
from app.raffle.validation import clean_source, validate_entry
from app.security.permissions import require_role

NO_STORE = {"Cache-Control": "no-store"}


def _cfg(name, default=None):
    return current_app.config.get(name, default)


def _parse_dt(value):
    if not value:
        return None
    moment = datetime.fromisoformat(str(value))
    return moment if moment.tzinfo else moment.replace(tzinfo=BOGOTA)


def _raffle() -> dict:
    return {
        "code": _cfg("RAFFLE_CODE", "V60-CASTILLO-2026"),
        "name": _cfg("RAFFLE_NAME", "Gran Sorteo Densa Niebla"),
    }


def _state() -> str:
    """open | upcoming | ended | inactive | unavailable (fechas mal configuradas)."""
    if not _cfg("RAFFLE_ACTIVE", True):
        return "inactive"
    try:
        starts, ends = _parse_dt(_cfg("RAFFLE_STARTS_AT")), _parse_dt(_cfg("RAFFLE_ENDS_AT"))
    except ValueError:
        current_app.logger.error("RAFFLE_STARTS_AT / RAFFLE_ENDS_AT no tienen formato ISO valido")
        return "unavailable"
    now = datetime.now(timezone.utc)
    if starts and now < starts:
        return "upcoming"
    if ends and now > ends:
        return "ended"
    return "open"


def _closed(state):
    status = {"upcoming": 200, "unavailable": 503}.get(state, 410)
    return render_template("raffle/raffle_closed.html", raffle=_raffle(), state=state), status, NO_STORE


def _error(message, status):
    return render_template("raffle/_raffle_error.html", message=message), status, NO_STORE


def _find_party(whatsapp: str):
    """Tercero existente con ese celular (en whatsapp o phone) o con el documento provisional. Bloquea la fila."""
    last10 = whatsapp[-10:]

    def digits(column):
        return func.right(func.regexp_replace(func.coalesce(column, ""), r"\D", "", "g"), 10)

    return db.session.scalars(
        select(Party)
        .where(or_(digits(Party.whatsapp) == last10, digits(Party.phone) == last10,
                   Party.document_number == provisional_document(whatsapp)))
        .order_by(Party.id).limit(1).with_for_update()
    ).first()


def _register(values: dict, code: str):
    """Devuelve ('created'|'updated'|'duplicate', entry_code)."""
    party = _find_party(values["whatsapp"])
    entry_code = new_entry_code()
    line = build_line(code, entry_code, values["source"], values["accepts_marketing"], values["city"])
    if party is not None:
        if has_participation(party.notes, code):
            return "duplicate", None
        party.notes = append_note(party.notes, line)
        if values["email"] and not party.email:
            party.email = values["email"]
        if not party.whatsapp:
            party.whatsapp = values["whatsapp"]
        if not party.has_role("CUSTOMER"):
            party.party_roles.append(PartyRole(role_code="CUSTOMER", valid_from=date.today()))
        outcome = "updated"
    else:
        party = Party(
            party_type="NATURAL", document_type="CC", document_number=provisional_document(values["whatsapp"]),
            legal_name=values["full_name"], first_name=values["full_name"], last_name="",
            email=values["email"], whatsapp=values["whatsapp"], payment_term_days=0, notes=line,
        )
        party.party_roles = [PartyRole(role_code="CUSTOMER", valid_from=date.today())]
        db.session.add(party)
        outcome = "created"
    db.session.commit()
    return outcome, entry_code


@raffle_bp.get("/")
def raffle_page():
    state = _state()
    if state != "open":
        return _closed(state)
    return render_template(
        "raffle/raffle_page.html", raffle=_raffle(), values={}, errors={},
        source=clean_source(request.args.get("source")),
    ), 200, NO_STORE


@raffle_bp.post("/inscripciones")
def create_raffle_entry():
    state = _state()
    if state != "open":
        return _error("Esta convocatoria no está disponible en este momento.", 503 if state == "unavailable" else 410)

    raffle = _raffle()
    values, errors = validate_entry(request.form)
    if errors:
        return render_template(
            "raffle/_raffle_form.html", raffle=raffle,
            values={**values, "whatsapp": values["whatsapp_raw"], "email": values["email"] or "", "city": values["city"] or ""},
            errors=errors, source=values["source"],
        ), 422, NO_STORE

    outcome = entry_code = None
    try:
        for _attempt in range(2):
            try:
                outcome, entry_code = _register(values, raffle["code"])
                break
            except IntegrityError:
                # Carrera: otra solicitud creo el mismo documento provisional; el segundo intento lo encuentra.
                db.session.rollback()
    except SQLAlchemyError:
        db.session.rollback()
        current_app.logger.exception("Error de base de datos al registrar una participacion")
        return _error("No pudimos registrar tu participación. Intenta nuevamente en unos minutos.", 503)

    if outcome is None:
        current_app.logger.error("No se pudo registrar la participacion tras reintentar")
        return _error("No pudimos completar tu registro. Intenta nuevamente.", 503)
    if outcome == "duplicate":
        return render_template("raffle/_raffle_already_registered.html", raffle=raffle), 409, NO_STORE

    current_app.logger.info("SORTEO %s participacion=%s party_action=%s", raffle["code"], entry_code, outcome)
    entry = {"full_name": values["full_name"], "entry_code": entry_code, "whatsapp": values["whatsapp"]}
    return render_template("raffle/_raffle_success.html", raffle=raffle, entry=entry), 201, NO_STORE


@raffle_bp.get("/admin")
@login_required
@require_role("ADMIN")
def raffle_entries():
    """Participantes = clientes con la marca del sorteo en sus notas. Datos personales: solo ADMIN."""
    raffle = _raffle()
    marker = tag(raffle["code"])
    parties = db.session.scalars(
        select(Party).where(Party.notes.contains(marker, autoescape=True)).order_by(Party.id.desc()).limit(500)
    ).all()
    total = db.session.scalar(select(func.count(Party.id)).where(Party.notes.contains(marker, autoescape=True))) or 0
    rows = [(party, parse_participation(party.notes, raffle["code"])) for party in parties]
    rows = [(party, info) for party, info in rows if info]
    return render_template(
        "raffle/raffle_entries.html", raffle=raffle, state=_state(), rows=rows, total=total,
        marketing_total=sum(1 for _, info in rows if info["accepts_marketing"]),
    ), 200, NO_STORE
