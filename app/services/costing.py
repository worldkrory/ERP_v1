"""Servicios de costeo de salidas de inventario."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.batch import Batch
from app.models.inventory import InventoryBalance
from app.models.product import Product
from app.models.setting import AppSetting


class CostingError(ValueError):
    """Error de dominio al resolver un costo."""


@dataclass(frozen=True)
class CostResolution:
    unit_cost: Decimal
    total_cost: Decimal
    method: str


def effective_costing_method(session: Session, product: Product) -> str:
    method = product.costing_method
    if method != "SYSTEM_DEFAULT":
        return method
    setting = session.scalar(
        select(AppSetting).where(AppSetting.key == "default_costing_method")
    )
    resolved = setting.typed_value if setting is not None else "WEIGHTED_AVERAGE"
    if resolved not in {"SPECIFIC_BATCH", "WEIGHTED_AVERAGE"}:
        raise CostingError(f"Metodo de costeo global invalido: {resolved!r}.")
    return str(resolved)


def resolve_outbound_cost(
    session: Session,
    product_id: int,
    batch_id: int | None,
    location_id: int,
    quantity_base: Decimal,
    at: date | None = None,
) -> CostResolution:
    """Resuelve el costo unitario y total para una salida."""
    quantity = Decimal(str(quantity_base))
    if quantity <= 0:
        raise CostingError("La cantidad a costear debe ser positiva.")

    product = session.get(Product, product_id)
    if product is None or not product.is_active:
        raise CostingError("El producto no existe o esta inactivo.")
    method = effective_costing_method(session, product)

    if method == "SPECIFIC_BATCH":
        if batch_id is None:
            raise CostingError("SPECIFIC_BATCH exige un lote.")
        batch = session.get(Batch, batch_id)
        if batch is None or batch.product_id != product_id:
            raise CostingError("El lote no pertenece al producto.")
        unit_cost = Decimal(batch.unit_cost)
    else:
        balances = session.scalars(
            select(InventoryBalance).where(
                InventoryBalance.product_id == product_id,
                InventoryBalance.location_id == location_id,
                InventoryBalance.quantity_base > 0,
            )
        ).all()
        available = sum((Decimal(balance.quantity_base) for balance in balances), Decimal("0"))
        total_value = sum((Decimal(balance.total_value) for balance in balances), Decimal("0"))
        if available < quantity:
            raise CostingError("No hay saldo suficiente para calcular el costo.")
        unit_cost = total_value / available if available else Decimal("0")

    return CostResolution(
        unit_cost=unit_cost,
        total_cost=unit_cost * quantity,
        method=method,
    )


__all__ = [
    "CostResolution",
    "CostingError",
    "effective_costing_method",
    "resolve_outbound_cost",
]