"""Validacion y limpieza de inscripciones al sorteo. Sin acceso a base de datos."""
from __future__ import annotations

import re

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
SOURCE_RE = re.compile(r"^[a-z0-9_-]{1,30}$")
CONTROL_RE = re.compile(r"[\x00-\x1f\x7f]")

MAX_NAME = 100  # se guarda en parties.first_name (100)
MAX_EMAIL = 255
MAX_CITY = 100


def clean_text(value: str | None) -> str:
    """Quita caracteres de control y espacios repetidos."""
    return " ".join(CONTROL_RE.sub(" ", value or "").split())


def normalize_whatsapp(value: str | None) -> str:
    digits = re.sub(r"\D+", "", value or "")
    if digits.startswith("57") and len(digits) == 12:
        return digits
    if len(digits) == 10 and digits.startswith("3"):
        return f"57{digits}"
    return digits


def clean_source(value: str | None) -> str:
    """Origen de la visita (campana, red social). Nunca confia en el texto crudo."""
    raw = (value or "").strip().lower()
    if not raw:
        return "whatsapp"
    return raw if SOURCE_RE.fullmatch(raw) else "directo"


def validate_entry(form) -> tuple[dict, dict]:
    """Devuelve (valores limpios, errores por campo). `form` es un mapeo tipo request.form."""
    full_name = clean_text(form.get("full_name"))
    whatsapp_raw = (form.get("whatsapp") or "").strip()[:40]
    whatsapp = normalize_whatsapp(whatsapp_raw)
    email = clean_text(form.get("email")).lower()
    city = clean_text(form.get("city"))

    values = {
        "full_name": full_name,
        "whatsapp": whatsapp,
        "whatsapp_raw": whatsapp_raw,
        "email": email or None,
        "city": city or None,
        "accepts_data_processing": form.get("accepts_data_processing") == "on",
        "accepts_marketing": form.get("accepts_marketing") == "on",
        "source": clean_source(form.get("source")),
    }
    errors: dict[str, str] = {}

    if len(full_name) < 3:
        errors["full_name"] = "Escribe tu nombre completo para registrar tu participación."
    elif len(full_name) > MAX_NAME:
        errors["full_name"] = f"Tu nombre admite máximo {MAX_NAME} caracteres."

    if not re.fullmatch(r"573\d{9}", whatsapp):
        errors["whatsapp"] = "Ingresa un número celular colombiano válido. Ejemplo: 300 123 4567."

    if email and (len(email) > MAX_EMAIL or not EMAIL_RE.fullmatch(email)):
        errors["email"] = "Revisa el formato de tu correo o déjalo vacío."

    if len(city) > MAX_CITY:
        errors["city"] = f"La ciudad admite máximo {MAX_CITY} caracteres."

    if not values["accepts_data_processing"]:
        errors["accepts_data_processing"] = "Necesitamos tu autorización para registrar la participación."

    return values, errors
