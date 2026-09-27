"""Rutas públicas de catálogo y carrito para Densa Niebla."""

from __future__ import annotations

from flask import Blueprint, flash, redirect, render_template, request, url_for

from app.services.cart_service import (
    CartError,
    add_cart_item,
    cart_item_count,
    get_cart,
    remove_cart_item,
    update_cart_item_quantity,
)
from app.services.catalog_service import (
    CatalogError,
    get_public_coffee,
    list_public_coffees,
)


storefront_bp = Blueprint("storefront", __name__)


@storefront_bp.get("/tienda")
def collection():
    """Mostrar la colección pública de cafés disponibles."""

    coffees = list_public_coffees()

    return render_template(
        "storefront/collection.html",
        coffees=coffees,
        cart_count=cart_item_count(),
    )


@storefront_bp.get("/tienda/<slug>")
def product_detail(slug: str):
    """Mostrar una ficha reusable de café comercial."""

    try:
        product = get_public_coffee(slug)
    except CatalogError:
        return render_template("404.html"), 404

    return render_template(
        "storefront/product_detail.html",
        product=product,
        cart_count=cart_item_count(),
    )


@storefront_bp.get("/carrito")
def cart():
    """Mostrar el carrito recalculado con precio y disponibilidad actuales."""

    cart_data = get_cart()

    return render_template(
        "storefront/cart.html",
        cart=cart_data,
        cart_count=cart_data["item_count"],
    )


@storefront_bp.post("/carrito/items")
def add_item():
    """Agregar una variante real del ERP al carrito de sesión."""

    try:
        product_id = int(request.form["product_id"])
        quantity = int(request.form.get("quantity", "1"))

        add_cart_item(product_id=product_id, quantity=quantity)
        flash("El café fue agregado a tu taza.", "success")

    except (KeyError, TypeError, ValueError, CartError) as exc:
        flash(str(exc), "error")

    next_url = request.form.get("next")

    if next_url and next_url.startswith("/"):
        return redirect(next_url)

    return redirect(url_for("storefront.cart"))


@storefront_bp.post("/carrito/items/<int:product_id>/quantity")
def update_item_quantity(product_id: int):
    """Actualizar cantidad de un producto sin confiar en el cliente."""

    try:
        quantity = int(request.form["quantity"])
        update_cart_item_quantity(product_id=product_id, quantity=quantity)
        flash("La cantidad fue actualizada.", "success")
    except (KeyError, TypeError, ValueError, CartError) as exc:
        flash(str(exc), "error")

    return redirect(url_for("storefront.cart"))


@storefront_bp.post("/carrito/items/<int:product_id>/remove")
def remove_item(product_id: int):
    """Quitar una presentación del carrito."""

    remove_cart_item(product_id=product_id)
    flash("El café fue retirado de tu taza.", "success")

    return redirect(url_for("storefront.cart"))