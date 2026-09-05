"""Notificaciones al grupo operativo mediante Telegram Bot API."""

from __future__ import annotations

import json
from urllib import parse, request

from flask import current_app


class TelegramError(RuntimeError):
    """Error controlado al enviar una notificación."""


def _call(method: str, payload: dict) -> dict:
    token = current_app.config.get("TELEGRAM_BOT_TOKEN")
    if not token or not current_app.config.get("TELEGRAM_CHAT_ID"):
        raise TelegramError("Telegram no está configurado.")
    url = f"https://api.telegram.org/bot{token}/{method}"
    body = json.dumps(payload).encode("utf-8")
    req = request.Request(url, data=body, headers={"Content-Type": "application/json"})
    try:
        with request.urlopen(req, timeout=12) as response:
            result = json.load(response)
    except Exception as exc:  # pragma: no cover - depende del servicio externo
        raise TelegramError("Telegram no respondió.") from exc
    if not result.get("ok"):
        raise TelegramError("Telegram rechazó la notificación.")
    return result["result"]


def notify_sale(sale) -> int:
    result = _call(
        "sendMessage",
        {
            "chat_id": current_app.config["TELEGRAM_CHAT_ID"],
            "text": (
                f"Nueva venta {sale.sale_number}\n"
                f"Cliente: {sale.party.display_name}\n"
                f"Total: {sale.currency} {sale.total:,.2f}\n"
                f"Canal: {sale.channel}\n"
                f"Referencia para conciliar: {sale.sale_number}"
            ),
        },
    )
    return int(result["message_id"])


def send_receipt(photo_url: str, caption: str) -> int:
    result = _call(
        "sendPhoto",
        {
            "chat_id": current_app.config["TELEGRAM_CHAT_ID"],
            "photo": photo_url,
            "caption": caption,
        },
    )
    return int(result["message_id"])


def notify_sale_cancelled(sale, reason: str, cancelled_by: str | None = None) -> int:
    """Notificar cancelación de venta a Telegram.
    
    Args:
        sale: Venta cancelada
        reason: Razón de la cancelación
        cancelled_by: Nombre/email del usuario que canceló
        
    Returns:
        int: ID del mensaje en Telegram
    """
    user_info = f"\nCancelada por: {cancelled_by}" if cancelled_by else ""
    
    result = _call(
        "sendMessage",
        {
            "chat_id": current_app.config["TELEGRAM_CHAT_ID"],
            "text": (
                f"⚠️ VENTA CANCELADA\n"
                f"Venta: {sale.sale_number}\n"
                f"Cliente: {sale.party.display_name}\n"
                f"Total: {sale.currency} {sale.total:,.2f}\n"
                f"Estado anterior: {sale.status}\n"
                f"Razón: {reason}"
                f"{user_info}\n"
                f"Timestamp: {sale.cancelled_at.strftime('%Y-%m-%d %H:%M:%S') if sale.cancelled_at else 'N/A'}"
            ),
            "parse_mode": "HTML",
        },
    )
    return int(result["message_id"])