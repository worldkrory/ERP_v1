"""Presentacion de productos vendidos. No escribe ni consulta la base de datos."""
from decimal import Decimal
from urllib.parse import urlsplit

from flask import url_for
from app.services.catalog_service import PUBLIC_COFFEES


def _quantity_label(value):
    value = format(Decimal(value), "f")
    if "." in value:
        value = value.rstrip("0").rstrip(".")
    return value.replace(".", ",")


def _image_url(product, catalog_images):
    if product is None:
        return None
    path = (product.image_path or "").strip()
    if not path:
        path = catalog_images.get(product.id, "")
    if not path:
        return None
    parsed = urlsplit(path)
    if parsed.scheme:
        return path if parsed.scheme in ("http", "https") and parsed.netloc else None
    if path.startswith("//"):
        return None
    path = path.replace("\\", "/").lstrip("/")
    if path.startswith("app/static/"):
        path = path[len("app/static/"):]
    elif path.startswith("static/"):
        path = path[len("static/"):]
    if not path or ".." in path.split("/"):
        return None
    return url_for("static", filename=path)


def build_sale_product_summaries(sales):
    """Requiere Sale.items, SaleItem.product y SaleItem.unit precargados."""
    catalog_images = {
        product_id: definition.hero_image
        for definition in PUBLIC_COFFEES.values()
        for product_id in definition.product_ids
    }
    result = {}
    for sale in sales:
        lines = []
        for item in sorted(sale.items, key=lambda line: line.id or 0):
            product = item.product
            lines.append({
                "name": item.description or (product.name if product else "Sin descripción"),
                "sku": product.sku if product else None,
                "quantity": _quantity_label(item.quantity),
                "unit": item.unit.code if item.unit else "Unidad no disponible",
                "image": _image_url(product, catalog_images),
            })
        result[sale.id] = lines
    return result
