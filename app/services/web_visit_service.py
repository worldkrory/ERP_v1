"""Servicios para registrar y notificar visitas a páginas públicas."""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass
from datetime import datetime, timezone

from flask import Request, current_app, session

from app.services.telegram_service import TelegramError, send_message


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class WebVisitEvent:
    page_name: str
    path: str
    full_path: str
    utm_source: str | None
    utm_medium: str | None
    utm_campaign: str | None
    utm_content: str | None
    utm_term: str | None
    referer: str | None
    visitor_hash: str
    visited_at: datetime


def _clean(value: str | None, max_length: int = 160) -> str | None:
    if not value:
        return None

    value = " ".join(value.strip().split())
    return value[:max_length] if value else None


def _client_ip(request: Request) -> str:
    """Usar proxy headers solo cuando estén controlados por tu servidor."""

    if current_app.config.get("TRUST_PROXY_HEADERS", False):
        forwarded_for = request.headers.get("X-Forwarded-For", "")
        if forwarded_for:
            return forwarded_for.split(",")[0].strip()

    return request.remote_addr or "unknown"


def _visitor_hash(request: Request) -> str:
    """Hash irreversible para identificar recurrencia sin guardar la IP."""

    secret = current_app.config["WEB_EVENT_HASH_SECRET"]
    raw_value = f"{secret}:{_client_ip(request)}:{request.user_agent.string}"

    return hashlib.sha256(raw_value.encode("utf-8")).hexdigest()[:16]


def build_web_visit_event(request: Request, *, page_name: str) -> WebVisitEvent:
    """Crear un evento de visita a partir del request Flask."""

    return WebVisitEvent(
        page_name=page_name,
        path=request.path,
        full_path=request.full_path.rstrip("?"),
        utm_source=_clean(request.args.get("utm_source"), 80),
        utm_medium=_clean(request.args.get("utm_medium"), 80),
        utm_campaign=_clean(request.args.get("utm_campaign"), 100),
        utm_content=_clean(request.args.get("utm_content"), 100),
        utm_term=_clean(request.args.get("utm_term"), 100),
        referer=_clean(request.referrer, 220),
        visitor_hash=_visitor_hash(request),
        visited_at=datetime.now(timezone.utc),
    )


def should_notify_visit(event: WebVisitEvent) -> bool:
    """Notificar una vez por página en cada sesión de navegador."""

    session_key = f"web_visit_alert:{event.path}"

    if session.get(session_key):
        return False

    session[session_key] = True
    session.modified = True
    return True


def _campaign_label(event: WebVisitEvent) -> str:
    values = [
        event.utm_source,
        event.utm_medium,
        event.utm_campaign,
    ]
    return " / ".join(value for value in values if value) or "Sin UTM"


def _build_telegram_message(event: WebVisitEvent) -> str:
    lines = [
        "☕ <b>Nueva visita a Densa Niebla</b>",
        f"<b>Página:</b> {event.page_name}",
        f"<b>Ruta:</b> <code>{event.full_path}</code>",
        f"<b>Campaña:</b> {_campaign_label(event)}",
        f"<b>Visitante:</b> <code>{event.visitor_hash}</code>",
        f"<b>Hora UTC:</b> {event.visited_at.strftime('%Y-%m-%d %H:%M:%S')}",
    ]

    if event.utm_content:
        lines.append(f"<b>Contenido:</b> {event.utm_content}")

    if event.utm_term:
        lines.append(f"<b>Término:</b> {event.utm_term}")

    if event.referer:
        lines.append(f"<b>Referer:</b> {event.referer}")

    return "\n".join(lines)


def notify_web_visit_safely(event: WebVisitEvent) -> None:
    """Enviar alerta sin afectar la experiencia del visitante."""

    try:
        send_message(
            _build_telegram_message(event),
            parse_mode="HTML",
        )
    except TelegramError:
        logger.warning(
            "No se pudo notificar visita web. page=%s path=%s",
            event.page_name,
            event.path,
            exc_info=True,
        )