"""Cotización de envío Inter Rapidísimo para el checkout."""
from __future__ import annotations

import csv
import logging
import math
import time
import unicodedata
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from functools import lru_cache
from pathlib import Path

import requests
from flask import current_app

log = logging.getLogger(__name__)

URL = "https://interrapidisimo.com/api/cotizador/cotizar"
ORIGEN_DANE = "17001000"  # Manizales; origen por defecto
FORMA_PAGO = 3            # confirma con la documentación
SERVICIO_ID = 3           # Mensajería estándar

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
CSV_CIUDADES = DATA_DIR / "ciudades_dane.csv"
CSV_TARIFAS = DATA_DIR / "tarifas_envio.csv"

RANGOS = [(2, 45000), (5, 60000), (9999, 75000)]  # (peso máx kg, valor mínimo)
MAX_DECLARED = 8_754_525

_CACHE: dict[tuple, tuple[float, dict]] = {}
_TTL = 3 * 3600


class ShippingError(Exception):
    pass


# ---------------------------------------------------------------- Ciudades

def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", s or "")
    return "".join(c for c in s if not unicodedata.combining(c)).lower().strip()


@lru_cache(maxsize=1)
def _ciudades() -> list[dict]:
    with open(CSV_CIUDADES, encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))  # codigo,nombre,departamento,busqueda


def search_cities(q: str, limit: int = 6) -> list[dict]:
    q = _norm(q)
    if len(q) < 3:
        return []
    starts = [c for c in _ciudades() if c["busqueda"].startswith(q)]
    contains = [c for c in _ciudades() if q in c["busqueda"] and c not in starts]
    return (starts + contains)[:limit]


def get_city(code: str) -> dict | None:
    return next((c for c in _ciudades() if c["codigo"] == code), None)


def find_city(name: str, department: str) -> dict | None:
    n, d = _norm(name), _norm(department)
    same_name = [c for c in _ciudades() if _norm(c["nombre"]) == n]
    for c in same_name:
        if _norm(c["departamento"]) == d:
            return c
    return same_name[0] if len(same_name) == 1 else None


# ------------------------------------------------------- Peso y declarado

def _cfg(key: str, default) -> Decimal:
    return Decimal(str(current_app.config.get(key, default)))


def cart_shipping_weight_kg(cart: dict) -> int:
    """Peso de despacho en kg enteros, mínimo 1."""
    default_g = _cfg("STOREFRONT_DEFAULT_BAG_G", 340)
    bag_tare = _cfg("STOREFRONT_BAG_TARE_G", 30)
    box_tare = _cfg("STOREFRONT_BOX_TARE_G", 150)

    total_g = Decimal(0)
    for item in cart["items"]:
        net = item["variant"].get("weight_g") or default_g
        total_g += (Decimal(net) + bag_tare) * item["quantity"]

    if total_g > 0:
        total_g += box_tare

    return max(1, math.ceil(total_g / 1000))


def declared_for(weight_kg: int, subtotal: int) -> int:
    """Valor declarado dentro del rango que exige Inter Rapidísimo."""
    minimo = next(v for tope, v in RANGOS if weight_kg <= tope)
    return min(max(subtotal, minimo), MAX_DECLARED)


# --------------------------------------------------------------- Respaldos

@lru_cache(maxsize=1)
def _tarifas() -> list[dict]:
    if not CSV_TARIFAS.exists():
        return []
    rows = []
    with open(CSV_TARIFAS, encoding="utf-8", newline="") as f:
        for r in csv.DictReader(f):
            precio = (r.get("precio") or "").strip()
            if not precio.replace(".", "", 1).isdigit():
                continue
            rows.append({
                "origen": r["origen"].strip(),
                "destino": r["destino"].strip().lower(),
                "peso_max": int(r["peso_max_kg"]),
                "precio": Decimal(precio),
            })
    return rows


def rate_for(origen: str, city: dict, weight_kg: int) -> Decimal | None:
    dep = "dep:" + _norm(city["departamento"])
    for o, d in (
        (origen, city["codigo"]), (origen, dep), (origen, "*"),
        ("*", dep), ("*", "*"),
    ):
        rows = sorted(
            (r for r in _tarifas() if r["origen"] == o and r["destino"] == d),
            key=lambda r: r["peso_max"],
        )
        for r in rows:
            if weight_kg <= r["peso_max"]:
                return r["precio"]
    return None


def fallback_rate(weight_kg: int) -> Decimal:
    """Estimación: primer kilo 20.000 y 4.900 por kg adicional (una sola ruta)."""
    return Decimal(20000 + max(0, weight_kg - 1) * 4900)


# --------------------------------------------------------- Inter Rapidísimo

def _parse_quote(data: dict) -> dict:
    if not data.get("operacionExitosa"):
        raise ShippingError(f"Respuesta no exitosa: {data.get('errores')}")
    svc = next(
        (s for s in data.get("resultado") or [] if s.get("idServicio") == SERVICIO_ID),
        None,
    )
    if svc is None:
        raise ShippingError("Mensajería estándar no disponible para esta ruta")
    return {
        "price": Decimal(str(svc["valorTotal"])),
        "freight": Decimal(str(svc["valorFlete"])),
        "insurance": Decimal(str(svc["valorPrimaSeguro"])),
        "days": svc.get("tiempoEntrega"),
    }

def padded_cart(cart: dict) -> dict:
    """Carrito ficticio con al menos SHIPPING_MIN_UNITS, solo para cotizar."""
    min_units = int(current_app.config.get("SHIPPING_MIN_UNITS", 2))
    missing = min_units - cart["item_count"]
    if missing <= 0 or not cart["items"]:
        return cart

    ref = max(cart["items"], key=lambda i: i["unit_price"])
    bumped = {**ref, "quantity": ref["quantity"] + missing}
    items = [bumped if i is ref else i for i in cart["items"]]
    return {
        **cart,
        "items": items,
        "item_count": cart["item_count"] + missing,
        "subtotal": cart["subtotal"] + ref["unit_price"] * missing,
    }

def _quote_remote(origen: str, destino: str, weight_kg: int, declared_value: int) -> dict:
    sid = "72f2edee-7bae-4e07-8797-0fa172bff3d1"
    # ""dcb49897-adb0-4cbc-b44c-db7f377d59e0""
    fecha = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat(
        timespec="milliseconds").replace("+00:00", "Z")
    body = {"guid": sid, "payload": {
        "fecha": fecha,
        "documentoRemitente": "", "documentoDestinatario": "",
        "esInterPay": False,
        "idCiudadOrigen": origen, "idCiudadDestino": destino,
        "largo": 0, "alto": 0, "ancho": 0,
        "pesoBascula": weight_kg, "valorDeclarado": declared_value,
        "idTipoEntrega": "1", "idFormaPago": FORMA_PAGO,
        "aplicaContraPago": False,
    }}
    r = requests.post(URL, json=body, timeout=8, headers={
        "accept": "*/*", "content-type": "application/json",
        "x-session-id": sid,
    })
    if r.status_code >= 400:
        raise ShippingError(f"HTTP {r.status_code}: {r.text[:300]}")
    return _parse_quote(r.json())


def quote_shipping(*, destino: str, weight_kg: int, declared_value: int,
                   origen: str = ORIGEN_DANE) -> dict:
    key = (origen, destino, weight_kg, declared_value)
    hit = _CACHE.get(key)
    if hit and time.time() - hit[0] < _TTL:
        return hit[1]

    try:
        out = {**_quote_remote(origen, destino, weight_kg, declared_value),
               "source": "interrapidisimo"}
        _CACHE[key] = (time.time(), out)
        return out
    except (requests.RequestException, ValueError, KeyError, ShippingError) as exc:
        log.warning("Cotizador IR falló %s->%s: %s", origen, destino, exc)

    city = get_city(destino)
    base = rate_for(origen, city, weight_kg) if city else None
    if base is not None:
        return {"price": base, "days": None, "source": "tarifa"}

    return {"price": fallback_rate(weight_kg), "days": None, "source": "respaldo"}