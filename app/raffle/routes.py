from __future__ import annotations

import re

from flask import render_template, request

from app.raffle import raffle_bp


def normalize_whatsapp(value: str) -> str:
    digits = re.sub(r"\D+", "", value or "")

    if digits.startswith("57") and len(digits) == 12:
        return digits

    if len(digits) == 10 and digits.startswith("3"):
        return f"57{digits}"

    return digits


@raffle_bp.get("/")
def raffle_page():
    return render_template(
        "raffle/raffle_page.html",
        raffle={
            "code": "V60-CASTILLO-2026",
            "name": "Gran Sorteo Densa Niebla",
            "prize_one": "Un V60 para preparar con pausa.",
            "prize_two": "Un café Castillo de Densa Niebla.",
        },
    )


@raffle_bp.post("/inscripciones")
def raffle_preview_entry():
    """
    Vista previa: valida y devuelve HTML para HTMX.
    No registra datos ni usa PostgreSQL todavía.
    """
    full_name = (request.form.get("full_name") or "").strip()
    whatsapp_raw = request.form.get("whatsapp") or ""
    whatsapp = normalize_whatsapp(whatsapp_raw)
    email = (request.form.get("email") or "").strip().lower()
    city = (request.form.get("city") or "").strip()

    accepts_data_processing = request.form.get("accepts_data_processing") == "on"
    accepts_marketing = request.form.get("accepts_marketing") == "on"

    errors: dict[str, str] = {}

    if len(full_name) < 3:
        errors["full_name"] = "Escribe tu nombre completo para dejar tu lugar registrado."

    if not re.fullmatch(r"573\d{9}", whatsapp):
        errors["whatsapp"] = (
            "Ingresa un celular colombiano válido. Ejemplo: 300 123 4567."
        )

    if not accepts_data_processing:
        errors["accepts_data_processing"] = (
            "Necesitamos tu autorización para procesar los datos de esta inscripción."
        )

    if errors:
        return render_template(
            "raffle/_raffle_form.html",
            values={
                "full_name": full_name,
                "whatsapp": whatsapp_raw,
                "email": email,
                "city": city,
                "accepts_marketing": accepts_marketing,
            },
            errors=errors,
            raffle_code="V60-CASTILLO-2026",
        ), 422

    return render_template(
        "raffle/_raffle_success.html",
        participant={
            "first_name": full_name.split()[0],
            "entry_code": "DN-DEMO-V60",
            "whatsapp_last_four": whatsapp[-4:],
            "accepts_marketing": accepts_marketing,
        },
    )