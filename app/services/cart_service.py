"""Carrito de sesión para la tienda pública Densa Niebla."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from flask import session

from app.services.catalog_service import (
    CatalogError,
    get_public_coffee,
    list_public_coffees,
)


class CartError(ValueError):
    """Error controlado del carrito."""


CART_SESSION_KEY = "storefront_cart"


def _raw_cart() -> dict[str, int]:
    """Obtener la estructura de carrito en sesión."""

    raw = session.get(CART_SESSION_KEY, {})

    if not isinstance(raw, dict):
        return {}

    return {
        str(product_id): int(quantity)
        for product_id, quantity in raw.items()
        if str(product_id).isdigit()
        and isinstance(quantity, int)
        and quantity > 0
    }


def _save_cart(cart: dict[str, int]) -> None:
    """Guardar el carrito de forma explícita en la sesión."""

    session[CART_SESSION_KEY] = cart
    session.modified = True


def _find_variant(product_id: int) -> tuple[dict, dict]:
    """Encontrar una variante pública real por su Product.id."""

    for coffee in list_public_coffees():
        for variant in coffee["variants"]:
            if variant["id"] == product_id:
                return coffee, variant

    raise CartError("La presentación seleccionada no existe en la tienda.")


def _validate_variant(product_id: int, quantity: int) -> tuple[dict, dict]:
    """Validar producto, cantidad, precio y disponibilidad presente."""

    if quantity <= 0:
        raise CartError("La cantidad debe ser mayor que cero.")

    try:
        coffee, variant = _find_variant(product_id)
    except CatalogError as exc:
        raise CartError(str(exc)) from exc

    if not variant["available"]:
        raise CartError(
            "Esta presentación no está disponible en este momento."
        )

    return coffee, variant


def add_cart_item(*, product_id: int, quantity: int) -> None:
    """Agregar una presentación o aumentar su cantidad."""

    cart = _raw_cart()
    current_quantity = cart.get(str(product_id), 0)
    new_quantity = current_quantity + quantity

    _validate_variant(product_id, new_quantity)

    cart[str(product_id)] = new_quantity
    _save_cart(cart)


def update_cart_item_quantity(*, product_id: int, quantity: int) -> None:
    """Actualizar cantidad o retirar si llega a cero."""

    cart = _raw_cart()

    if str(product_id) not in cart:
        raise CartError("Esta presentación no está en tu carrito.")

    if quantity <= 0:
        cart.pop(str(product_id), None)
        _save_cart(cart)
        return

    _validate_variant(product_id, quantity)

    cart[str(product_id)] = quantity
    _save_cart(cart)


def remove_cart_item(product_id: int) -> None:
    """Retirar una presentación del carrito."""

    cart = _raw_cart()
    cart.pop(str(product_id), None)
    _save_cart(cart)


def cart_item_count() -> int:
    """Contar unidades, no líneas, para el encabezado."""

    return sum(_raw_cart().values())


def get_cart() -> dict:
    """Reconstruir carrito con datos vigentes desde el servidor."""

    raw = _raw_cart()
    items = []
    invalid_product_ids = []
    subtotal = Decimal("0")

    for product_id_text, quantity in raw.items():
        product_id = int(product_id_text)

        try:
            coffee, variant = _validate_variant(product_id, quantity)
        except CartError:
            invalid_product_ids.append(product_id_text)
            continue

        unit_price = Decimal(variant["price_cop"])
        line_total = unit_price * quantity

        items.append(
            {
                "product_id": product_id,
                "coffee": coffee,
                "variant": variant,
                "quantity": quantity,
                "unit_price": unit_price,
                "line_total": line_total,
            }
        )

        subtotal += line_total

    if invalid_product_ids:
        for product_id_text in invalid_product_ids:
            raw.pop(product_id_text, None)

        _save_cart(raw)

    threshold = Decimal(
        str(
            items[0]["coffee"]["shipping"]["free_shipping_threshold_cop"]
            if items
            else 120000
        )
    )

    remaining_for_free_shipping = max(threshold - subtotal, Decimal("0"))

    return {
        "items": items,
        "item_count": sum(item["quantity"] for item in items),
        "subtotal": subtotal,
        "shipping_threshold": threshold,
        "remaining_for_free_shipping": remaining_for_free_shipping,
        "qualifies_for_free_shipping": bool(items) and subtotal >= threshold,
    }