from app.raffle import raffle_bp
app.register_blueprint(raffle_bp)

from __future__ import annotations

import re
import secrets

from flask import current_app, render_template, request
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.extensions import db
from app.models.raffle import Raffle, RaffleEntry
from app.raffle import raffle_bp


RAFFLE_CODE = "V60-CASTILLO-2026"


def normalize_whatsapp(value: str) -> str:
    digits = re.sub(r"\D+", "", value or "")

    if digits.startswith("57") and len(digits) == 12:
        return digits

    if len(digits) == 10 and digits.startswith("3"):
        return f"57{digits}"

    return digits


def get_active_raffle() -> Raffle | None:
    return db.session.scalar(
        select(Raffle).where(
            Raffle.code == RAFFLE_CODE,
            Raffle.is_active.is_(True),
        )
    )


@raffle_bp.get("/")
def raffle_page():
    raffle = get_active_raffle()

    if raffle is None:
        return render_template(
            "raffle/raffle_closed.html",
            raffle=None,
        ), 404

    return render_template(
        "raffle/raffle_page.html",
        raffle=raffle,
    )


@raffle_bp.post("/inscripciones")
def create_raffle_entry():
    raffle = get_active_raffle()

    if raffle is None:
        return render_template(
            "raffle/_raffle_error.html",
            message="Esta convocatoria ya no está disponible.",
        ), 410

    full_name = (request.form.get("full_name") or "").strip()
    whatsapp = normalize_whatsapp(request.form.get("whatsapp") or "")
    email = (request.form.get("email") or "").strip().lower() or None
    city = (request.form.get("city") or "").strip() or None

    accepts_data_processing = request.form.get("accepts_data_processing") == "on"
    accepts_marketing = request.form.get("accepts_marketing") == "on"

    errors: dict[str, str] = {}

    if len(full_name) < 3:
        errors["full_name"] = "Escribe tu nombre completo para registrar tu participación."

    if not re.fullmatch(r"573\d{9}", whatsapp):
        errors["whatsapp"] = (
            "Ingresa un número celular colombiano válido. "
            "Ejemplo: 300 123 4567."
        )

    if not accepts_data_processing:
        errors["accepts_data_processing"] = (
            "Necesitamos tu autorización para registrar la participación."
        )

    if errors:
        return render_template(
            "raffle/_raffle_form.html",
            raffle=raffle,
            values={
                "full_name": full_name,
                "whatsapp": request.form.get("whatsapp") or "",
                "email": email or "",
                "city": city or "",
                "accepts_marketing": accepts_marketing,
            },
            errors=errors,
        ), 422

    entry = RaffleEntry(
        raffle_id=raffle.id,
        entry_code=f"DN-{secrets.token_hex(4).upper()}",
        full_name=full_name,
        whatsapp=whatsapp,
        email=email,
        city=city,
        accepts_data_processing=True,
        accepts_marketing=accepts_marketing,
        source=request.form.get("source") or "whatsapp",
    )

    try:
        db.session.add(entry)
        db.session.commit()
    except IntegrityError:
        db.session.rollback()

        return render_template(
            "raffle/_raffle_already_registered.html",
            raffle=raffle,
            whatsapp=whatsapp,
        ), 409

    return render_template(
        "raffle/_raffle_success.html",
        raffle=raffle,
        entry=entry,
    ), 201

