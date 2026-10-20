"""Rutas públicas de catálogo y carrito para Densa Niebla."""

from __future__ import annotations

from flask import Blueprint, flash, redirect, render_template, request, url_for, session, current_app
from decimal import Decimal

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
from app.services.shipping_service import (
    ORIGEN_DANE, cart_shipping_weight_kg, declared_for, get_city, quote_shipping, search_cities, padded_cart
)

from app.services.fulfillment_service import candidate_origins, explain_origins


storefront_bp = Blueprint("storefront", __name__)

@storefront_bp.get("/checkout")
def checkout():
    cart_data = get_cart()
    if not cart_data["items"]:
        flash("Tu taza está vacía.", "error")
        return redirect(url_for("storefront.cart"))
    return render_template("storefront/checkout.html",
                           cart=cart_data, cart_count=cart_data["item_count"])


@storefront_bp.get("/checkout/ciudades")
def checkout_cities():
    q = request.args.get("ciudad_q", "")
    return render_template("storefront/_cities.html", cities=search_cities(q))

RANGOS = [(2, 45000), (5, 60000), (9999, 75000)]

def declared_for(weight_kg: float, subtotal: int) -> int:
    minimo = next(m for tope, m in RANGOS if weight_kg <= tope)
    return min(max(subtotal, minimo), 8_754_525)

@storefront_bp.post("/checkout/cotizar")
def checkout_quote():
    cart_data = get_cart()
    city = get_city(request.form.get("ciudad_codigo", ""))

    if not cart_data["items"] or not city:
        return render_template("storefront/_quote.html", error=True), 400

    quote_cart = padded_cart(cart_data)
    weight = cart_shipping_weight_kg(quote_cart)
    declared = declared_for(weight, int(quote_cart["subtotal"]))

    quotes = [
        (loc, quote_shipping(origen=dane, destino=city["codigo"],
                             weight_kg=weight, declared_value=declared))
        for loc, dane in candidate_origins(cart_data)
    ]

    if quotes:
        origin, result = min(quotes, key=lambda t: t[1]["price"])
        session["checkout_origin_id"] = origin.id
    else:
        origin = None
        session.pop("checkout_origin_id", None)
        result = quote_shipping(origen=ORIGEN_DANE, destino=city["codigo"],
                                weight_kg=weight, declared_value=declared)

    if current_app.debug:
        current_app.logger.info("Origenes: %s | elegido: %s",
                                explain_origins(cart_data),
                                origin.code if origin else "POR DEFECTO")

    free = cart_data["qualifies_for_free_shipping"]
    min_charge = Decimal(str(current_app.config.get("SHIPPING_MIN_CHARGE_COP", 0)))
    charged = 0 if free else max(result["price"], min_charge)

    return render_template(
        "storefront/_quote.html",
        city=city, origin=origin, shipping=charged, real_cost=result["price"],
        free=free, source=result["source"],
        total=cart_data["subtotal"] + charged, error=False,
    )

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