"""Servicios de conversion de unidades del ERP."""

from __future__ import annotations

from collections import deque
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.unit import UnitConversion, UnitOfMeasure


class UnitConversionError(ValueError):
    """Error de dominio al convertir cantidades."""


def _conversion_graph(
    session: Session,
    product_id: int | None = None,
) -> dict[int, list[tuple[int, Decimal]]]:
    conversions = session.scalars(
        select(UnitConversion).where(
            UnitConversion.is_active.is_(True),
            (UnitConversion.product_id == product_id)
            | (UnitConversion.product_id.is_(None)),
        )
    ).all()

    graph: dict[int, list[tuple[int, Decimal]]] = {}
    for conversion in conversions:
        graph.setdefault(conversion.from_unit_id, []).append(
            (conversion.to_unit_id, Decimal(conversion.factor))
        )
    return graph


def get_conversion_factor(
    session: Session,
    from_unit_id: int,
    to_unit_id: int,
    product_id: int | None = None,
) -> Decimal:
    """Devuelve el factor multiplicativo entre dos unidades."""
    if from_unit_id == to_unit_id:
        return Decimal("1")

    units = session.scalars(
        select(UnitOfMeasure).where(
            UnitOfMeasure.id.in_([from_unit_id, to_unit_id]),
            UnitOfMeasure.is_active.is_(True),
        )
    ).all()
    units_by_id = {unit.id: unit for unit in units}
    if len(units_by_id) != 2:
        raise UnitConversionError("Una de las unidades no existe o esta inactiva.")
    if not units_by_id[from_unit_id].same_dimension_as(units_by_id[to_unit_id]):
        raise UnitConversionError("No se pueden convertir dimensiones diferentes.")

    graph = _conversion_graph(session, product_id)
    queue: deque[tuple[int, Decimal]] = deque([(from_unit_id, Decimal("1"))])
    visited = {from_unit_id}
    while queue:
        current_id, accumulated = queue.popleft()
        for next_id, factor in graph.get(current_id, []):
            if next_id == to_unit_id:
                return accumulated * factor
            if next_id not in visited:
                visited.add(next_id)
                queue.append((next_id, accumulated * factor))

    raise UnitConversionError(
        f"No existe conversion entre {from_unit_id} y {to_unit_id}."
    )


def convert_quantity(
    session: Session,
    quantity: Any,
    from_unit_id: int,
    to_unit_id: int,
    product_id: int | None = None,
) -> Decimal:
    """Convierte una cantidad usando Decimal y sin redondeo intermedio."""
    amount = Decimal(str(quantity))
    if amount < 0:
        raise UnitConversionError("La cantidad no puede ser negativa.")
    return amount * get_conversion_factor(
        session, from_unit_id, to_unit_id, product_id
    )


__all__ = ["UnitConversionError", "convert_quantity", "get_conversion_factor"]