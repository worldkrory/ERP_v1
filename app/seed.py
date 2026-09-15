from __future__ import annotations

from datetime import date
from decimal import Decimal

import click
import os
from flask import current_app
from sqlalchemy import select

from app.extensions import db
from app.models import (
    InventoryLocation,
    Party,
    PartyRole,
    Product,
    ProductCategory,
    Role,
    UnitConversion,
    UnitOfMeasure,
)


def register_seed_commands(app):
    @app.cli.group("seed")
    def seed_group():
        """Carga datos maestros idempotentes del ERP."""

    @seed_group.command("initial")
    def seed_initial():
        """Prepara catálogos mínimos para compras, inventario y ventas."""
        if not current_app.config.get("TESTING") and os.getenv("ALLOW_SEED_INITIAL") != "1":
            raise click.ClickException(
                "Siembra bloqueada fuera de pruebas. Usa el panel o define "
                "ALLOW_SEED_INITIAL=1 de forma consciente."
            )
        units = _seed_units()
        _seed_conversions(units)
        _seed_roles()
        _seed_locations()
        supplier = _seed_supplier()
        _seed_products(units)
        db.session.commit()
        click.echo(
            "Datos maestros listos: "
            f"{len(units)} unidades, proveedor {supplier.document_number}, "
            "bodega BODEGA_PRINCIPAL y productos operativos."
        )


def _get_or_create(model, identity: dict, values: dict | None = None):
    instance = db.session.scalar(select(model).filter_by(**identity))
    if instance is None:
        instance = model(**identity, **(values or {}))
        db.session.add(instance)
        db.session.flush()
    return instance


def _seed_units() -> dict[str, UnitOfMeasure]:
    definitions = (
        ("KG", "Kilogramo", "MASS", True),
        ("LB", "Libra", "MASS", False),
        ("G", "Gramo", "MASS", False),
        ("ARROBA", "Arroba", "MASS", False),
        ("CARGA", "Carga", "MASS", False),
        ("SACO", "Saco", "MASS", False),
        ("UN", "Unidad", "COUNT", True),
        ("CAJA", "Caja", "COUNT", False),
        ("HORA", "Hora", "TIME", True),
    )
    return {
        code: _get_or_create(
            UnitOfMeasure,
            {"code": code},
            {"name": name, "dimension": dimension, "is_base_for_dimension": is_base},
        )
        for code, name, dimension, is_base in definitions
    }


def _seed_conversions(units: dict[str, UnitOfMeasure]):
    conversions = (
        ("KG", "LB", Decimal("2.2046226218")),
        ("KG", "G", Decimal("1000")),
        ("ARROBA", "KG", Decimal("12.5")),
        ("CARGA", "KG", Decimal("125")),
        ("SACO", "KG", Decimal("70")),
        ("CAJA", "UN", Decimal("1")),
    )
    for from_code, to_code, factor in conversions:
        _get_or_create(
            UnitConversion,
            {"from_unit_id": units[from_code].id, "to_unit_id": units[to_code].id, "product_id": None},
            {"factor": factor},
        )


def _seed_roles():
    roles = (
        ("ADMIN", "Administrador"),
        ("VENTAS", "Ventas"),
        ("PRODUCCION", "Producción"),
        ("INVENTARIO", "Inventario"),
        ("CONTABILIDAD", "Contabilidad"),
        ("CONSULTA", "Consulta"),
        ("COMPRAS", "Compras"),
    )
    for code, name in roles:
        _get_or_create(Role, {"code": code}, {"name": name, "is_system": True})


def _seed_locations():
    _get_or_create(
        InventoryLocation,
        {"code": "BODEGA_PRINCIPAL"},
        {"name": "Bodega principal", "location_type": "WAREHOUSE"},
    )
    _get_or_create(
        InventoryLocation,
        {"code": "SCRAP"},
        {"name": "Mermas y desperdicios", "location_type": "SCRAP"},
    )


def _seed_supplier() -> Party:
    supplier = _get_or_create(
        Party,
        {"document_type": "CC", "document_number": "GUAVATA-001"},
        {
            "party_type": "NATURAL",
            "legal_name": "Caficultor de Guavatá",
            "first_name": "Caficultor",
            "last_name": "de Guavatá",
        },
    )
    for role_code in ("SUPPLIER", "COFFEE_GROWER"):
        _get_or_create(
            PartyRole,
            {"party_id": supplier.id, "role_code": role_code, "valid_from": date.today()},
        )
    return supplier


def _seed_products(units: dict[str, UnitOfMeasure]):
    raw_category = _get_or_create(ProductCategory, {"code": "CAFE_VERDE"}, {"name": "Café y materias primas"})
    supply_category = _get_or_create(ProductCategory, {"code": "EMPAQUES"}, {"name": "Empaques e insumos"})
    _get_or_create(
        Product,
        {"sku": "CAFE-PERGAMINO"},
        {
            "name": "Café pergamino seco",
            "product_kind": "RAW_MATERIAL",
            "category_id": raw_category.id,
            "base_unit_id": units["KG"].id,
            "purchase_unit_id": units["ARROBA"].id,
            "is_purchasable": True,
            "is_sellable": False,
            "is_produced": True,
            "costing_method": "SPECIFIC_BATCH",
            "tracks_batches": True,
        },
    )
    _get_or_create(
        Product,
        {"sku": "BOLSA-340G"},
        {
            "name": "Bolsa para café 340 g",
            "product_kind": "SUPPLY",
            "category_id": supply_category.id,
            "base_unit_id": units["UN"].id,
            "purchase_unit_id": units["UN"].id,
            "is_purchasable": True,
            "is_sellable": False,
            "is_produced": False,
            "costing_method": "WEIGHTED_AVERAGE",
            "tracks_batches": False,
        },
    )


__all__ = ["register_seed_commands"]