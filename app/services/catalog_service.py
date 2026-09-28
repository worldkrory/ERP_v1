"""Catálogo público de café conectado al ERP."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any

from flask import current_app
from sqlalchemy import func, select
from sqlalchemy.orm import joinedload

from app.extensions import db
from app.models.inventory import InventoryBalance
from app.models.price import PriceList, PriceListItem
from app.models.product import Product
from app.services.units import UnitConversionError, convert_quantity


class CatalogError(ValueError):
    """Error controlado al resolver el catálogo público."""


@dataclass(frozen=True)
class PublicCoffeeDefinition:
    """Contenido editorial que agrupa productos operativos reales."""

    slug: str
    name: str
    subtitle: str
    collection_label: str
    short_story: str
    product_ids: tuple[int, ...]
    hero_image: str
    gallery: tuple[dict[str, str], ...]
    origin: dict[str, Any]
    coffee: dict[str, Any]
    profile: dict[str, Any]
    related_slugs: tuple[str, ...]


PUBLIC_COFFEES: dict[str, PublicCoffeeDefinition] = {
    "origen-castillo": PublicCoffeeDefinition(
        slug="origen-castillo",
        name="Origen Castillo",
        subtitle="Guavatá, Santander",
        collection_label="Café de finca · Colombia",
        short_story=(
            "Un café lavado que pone el territorio al frente: "
            "cítricos amarillos, azúcar morena y una taza que evoluciona."
        ),
        product_ids=(2, 3),
        hero_image="img/products/castillo/bolsa-frontal.jpg",
        gallery=(
            {
                "src": "img/products/castillo/bolsa-frontal.jpg",
                "alt": "Bolsa de Origen Castillo de Densa Niebla",
            },
            {
                "src": "img/products/castillo/finca-guavata.jpg",
                "alt": "Paisaje cafetero de Guavatá, Santander",
            },
        ),
        origin={
            "municipality": "Guavatá",
            "region": "Santander",
            "country": "Colombia",
            "altitude_masl": 1900,
        },
        coffee={
            "variety": "Castillo",
            "process": "Lavado",
            "drying": "Al sol",
            "roast": "Medio",
        },
        profile={
            "score": Decimal("84.25"),
            "score_label": "Puntaje de perfil",
            "evaluated_at": "2026-08-05",
            "notes": (
                "Cítricos amarillos",
                "Azúcar morena",
                "Dulzor balanceado",
            ),
            "temperature_story": {
                "hot": "Jugoso desde el primer sorbo.",
                "warm": "Una pausa más seca y contemplativa.",
                "cold": "La jugosidad regresa.",
            },
        },
        related_slugs=("bourbon-rosado",),
    ),
    "bourbon-rosado": PublicCoffeeDefinition(
        slug="bourbon-rosado",
        name="Bourbon Rosado",
        subtitle="Guavatá, Santander",
        collection_label="Café especial · Microlote",
        short_story=(
            "Un microlote nacido entre montaña, neblina y manos "
            "que conocen la tierra."
        ),
        product_ids=(34, 35),
        hero_image="img/products/bourbon-rosado/bolsa-frontal.jpg",
        gallery=(
            {
                "src": "img/products/bourbon-rosado/bolsa-frontal.jpg",
                "alt": "Bolsa de Bourbon Rosado de Densa Niebla",
            },
        ),
        origin={
            "municipality": "Guavatá",
            "region": "Santander",
            "country": "Colombia",
            "altitude_masl": None,
        },
        coffee={
            "variety": "Bourbon Rosado",
            "process": "Lavado",
            "drying": None,
            "roast": "Medio Ligero",
        },
        profile={
            "score": None,
            "score_label": None,
            "evaluated_at": None,
            "notes": (),
            "temperature_story": {},
        },
        related_slugs=("origen-castillo",),
    ),
}


def _location_ids() -> tuple[int, ...]:
    location_ids = current_app.config.get("STOREFRONT_STOCK_LOCATION_IDS", ())

    if not location_ids:
        raise CatalogError(
            "La tienda no tiene ubicaciones de inventario configuradas."
        )

    return tuple(int(value) for value in location_ids)


def _price_channel() -> str:
    return current_app.config.get("STOREFRONT_PRICE_CHANNEL", "RETAIL")


def _available_quantity_base(product_id: int) -> Decimal:
    """Sumar saldo positivo de un producto en unidad base.

    InventoryBalance.quantity_base siempre está expresado en la unidad
    base del producto. Esta función no convierte ni redondea.
    """

    quantity_base = db.session.scalar(
        select(
            func.coalesce(func.sum(InventoryBalance.quantity_base), 0)
        ).where(
            InventoryBalance.product_id == product_id,
            InventoryBalance.location_id.in_(_location_ids()),
            InventoryBalance.quantity_base > 0,
        )
    )

    return Decimal(str(quantity_base or 0))


def _available_sale_units(product: Product) -> int:
    """Calcular unidades completas disponibles para vender.

    Para productos finales inventariados en la misma unidad de venta,
    por ejemplo UND → UND, el saldo base ya representa bolsas.

    Para productos con unidad de venta distinta a la unidad base, intenta
    una conversión solamente si ambas unidades comparten dimensión. Si no
    existe, no publica disponibilidad comprable para evitar sobreventa.
    """

    quantity_base = _available_quantity_base(product.id)

    if quantity_base <= 0:
        return 0

    if product.effective_sales_unit_id == product.base_unit_id:
        return int(quantity_base)

    try:
        sale_unit_in_base = convert_quantity(
            db.session,
            Decimal("1"),
            product.effective_sales_unit_id,
            product.base_unit_id,
            product.id,
        )
    except UnitConversionError:
        return 0

    if sale_unit_in_base <= 0:
        return 0

    return int(quantity_base // sale_unit_in_base)


def _default_price_list(day: date) -> PriceList:
    price_list = db.session.scalar(
        select(PriceList).where(
            PriceList.channel == _price_channel(),
            PriceList.is_default.is_(True),
            PriceList.is_active.is_(True),
        )
    )

    if price_list is None or not price_list.covers(day):
        raise CatalogError(
            "No existe una lista de precios pública vigente."
        )

    return price_list


def _resolve_public_price(product: Product, day: date) -> Decimal | None:
    """Obtener precio vigente para la unidad efectiva de venta."""

    price_list = _default_price_list(day)

    candidates = db.session.scalars(
        select(PriceListItem).where(
            PriceListItem.price_list_id == price_list.id,
            PriceListItem.product_id == product.id,
            PriceListItem.unit_id == product.effective_sales_unit_id,
            PriceListItem.is_active.is_(True),
        )
    ).all()

    item = next(
        (
            candidate
            for candidate in candidates
            if candidate.covers(day)
            and candidate.covers_quantity(Decimal("1"))
        ),
        None,
    )

    return Decimal(item.unit_price) if item else None


def _variant_from_product(product: Product, day: date) -> dict[str, Any]:
    """Traducir un Product real a una variante pública de la tienda."""

    profile = product.coffee_profile
    price = _resolve_public_price(product, day)
    available_units = _available_sale_units(product)

    presentation = (
        profile.grind_type.replace("_", " ").title()
        if profile and profile.grind_type
        else product.name
    )

    weight_g = (
        Decimal(profile.packaging_grams)
        if profile and profile.packaging_grams is not None
        else None
    )

    available = (
        product.is_active
        and product.is_sellable
        and price is not None
        and available_units > 0
    )

    if not product.is_active or not product.is_sellable:
        stock_label = "No disponible"
    elif price is None:
        stock_label = "Precio no disponible"
    elif available_units <= 0:
        stock_label = "Agotado"
    elif available_units <= 3:
        stock_label = f"Disponibles: {available_units}"
    else:
        stock_label = "Disponible"

    return {
        "id": product.id,
        "sku": product.sku,
        "label": (
            f"{presentation} · {format(weight_g, 'f').rstrip('0').rstrip('.')} g"
            if weight_g is not None
            else presentation
        ),
        "presentation": presentation,
        "weight_g": weight_g,
        "price_cop": price,
        "available": available,
        "available_units": available_units,
        "stock_label": stock_label,
    }


def _load_products(product_ids: tuple[int, ...]) -> list[Product]:
    if not product_ids:
        return []

    products = db.session.scalars(
        select(Product)
        .options(joinedload(Product.coffee_profile))
        .where(Product.id.in_(product_ids))
    ).unique().all()

    products_by_id = {product.id: product for product in products}

    return [
        products_by_id[product_id]
        for product_id in product_ids
        if product_id in products_by_id
    ]


def _serialize_coffee(
    definition: PublicCoffeeDefinition,
    *,
    include_related: bool,
) -> dict[str, Any]:
    day = date.today()
    products = _load_products(definition.product_ids)
    variants = [_variant_from_product(product, day) for product in products]

    sellable_variants = [
        variant for variant in variants
        if variant["price_cop"] is not None
    ]

    price_from = min(
        (variant["price_cop"] for variant in sellable_variants),
        default=None,
    )

    coffee = {
        "id": definition.slug,
        "slug": definition.slug,
        "name": definition.name,
        "subtitle": definition.subtitle,
        "collection_label": definition.collection_label,
        "short_story": definition.short_story,
        "hero_image": definition.hero_image,
        "gallery": definition.gallery,
        "origin": definition.origin,
        "coffee": definition.coffee,
        "profile": definition.profile,
        "variants": variants,
        "price_from_cop": price_from,
        "available": any(variant["available"] for variant in variants),
        "shipping": {
            "message": "Envíos desde Guavatá, Manizales, Bogotá y Cali a toda Colombia.",
            "dispatch": "Despachamos de lunes a sábado.",
            "free_shipping_threshold_cop": current_app.config.get(
                "STOREFRONT_FREE_SHIPPING_THRESHOLD_COP",
                120000,
            ),
        },
        "seo": {
            "title": f"{definition.name} | Densa Niebla",
            "description": definition.short_story,
        },
        "related_products": [],
    }

    if include_related:
        coffee["related_products"] = [
            _serialize_coffee(
                PUBLIC_COFFEES[related_slug],
                include_related=False,
            )
            for related_slug in definition.related_slugs
            if related_slug in PUBLIC_COFFEES
        ]

    return coffee


def get_public_coffee(slug: str) -> dict[str, Any]:
    """Obtener una ficha pública por slug."""

    definition = PUBLIC_COFFEES.get(slug)

    if definition is None:
        raise CatalogError("El café solicitado no existe.")

    return _serialize_coffee(definition, include_related=True)


def list_public_coffees() -> list[dict[str, Any]]:
    """Obtener la colección de cafés para la página /tienda."""

    return [
        _serialize_coffee(definition, include_related=False)
        for definition in PUBLIC_COFFEES.values()
    ]