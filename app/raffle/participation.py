"""Participacion en el sorteo registrada sobre el tercero (cliente). Funciones puras, sin base de datos.

La participacion se guarda como una linea en `parties.notes`:
[SORTEO:CODIGO] DN-XXXXXXXX | 2026-10-18 14:30 | fuente=tiktok | datos=si | novedades=si | ciudad=Manizales
"""
from __future__ import annotations

import re
import secrets
from datetime import datetime, timedelta, timezone

BOGOTA = timezone(timedelta(hours=-5))  # Colombia no usa horario de verano
PROVISIONAL_PREFIX = "SORTEO-"
_UNSAFE = re.compile(r"[|\[\]\r\n]+")


def tag(raffle_code: str) -> str:
    return f"[SORTEO:{raffle_code}]"


def provisional_document(whatsapp: str) -> str:
    """Documento provisional (max 30 caracteres) mientras no se conozca el real."""
    return f"{PROVISIONAL_PREFIX}{whatsapp}"[:30]


def is_provisional(document_number: str | None) -> bool:
    return (document_number or "").startswith(PROVISIONAL_PREFIX)


def new_entry_code() -> str:
    return f"DN-{secrets.token_hex(4).upper()}"


def _safe(text: str | None) -> str:
    return " ".join(_UNSAFE.sub(" ", text or "").split())


def build_line(raffle_code: str, entry_code: str, source: str, accepts_marketing: bool,
               city: str | None, when: datetime | None = None) -> str:
    when = (when or datetime.now(BOGOTA)).astimezone(BOGOTA)
    parts = [
        f"{tag(raffle_code)} {entry_code}",
        when.strftime("%Y-%m-%d %H:%M"),
        f"fuente={_safe(source) or 'directo'}",
        "datos=si",
        f"novedades={'si' if accepts_marketing else 'no'}",
    ]
    if city:
        parts.append(f"ciudad={_safe(city)}")
    return " | ".join(parts)


def append_note(notes: str | None, line: str) -> str:
    return f"{notes.rstrip()}\n{line}" if notes and notes.strip() else line


def has_participation(notes: str | None, raffle_code: str) -> bool:
    prefix = tag(raffle_code)
    return any(row.strip().startswith(prefix) for row in (notes or "").splitlines())


def parse_participation(notes: str | None, raffle_code: str) -> dict | None:
    prefix = tag(raffle_code)
    for row in (notes or "").splitlines():
        row = row.strip()
        if not row.startswith(prefix):
            continue
        parts = [piece.strip() for piece in row.split("|")]
        data = {"entry_code": parts[0][len(prefix):].strip(), "registered_at": parts[1] if len(parts) > 1 else "",
                "source": "", "accepts_marketing": False, "city": ""}
        for piece in parts[2:]:
            key, _, value = piece.partition("=")
            if key == "fuente":
                data["source"] = value
            elif key == "novedades":
                data["accepts_marketing"] = value == "si"
            elif key == "ciudad":
                data["city"] = value
        return data
    return None
