"""Modulo Impuestos: taxes.

Seccion 4.4 del ERD logico v1.0.

Las tarifas cambian por reforma tributaria, por eso la tabla lleva vigencia:
una factura emitida antes de un cambio debe seguir mostrando la tarifa vigente
a su fecha.
"""

from __future__ import annotations

import datetime as _dt
from typing import TYPE_CHECKING, Optional

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Index,
    Numeric,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import PK, Base, Percent, enum_check, validity_check
from app.models.mixins import ActiveMixin, TimestampMixin, ValidityMixin

if TYPE_CHECKING:
    from app.models.product import Product

TAX_TYPES: tuple[str, ...] = (
    "IVA",
    "INC",
    "RETEFUENTE",
    "RETEIVA",
    "RETEICA",
    "NONE",
)


class Tax(TimestampMixin, ActiveMixin, ValidityMixin, Base):
    """Tributo aplicable a un producto o linea de documento, con vigencia.

    Seccion 4.4 del ERD. La tarifa se guarda como fraccion: 0.19 = 19%.

    Invariante de servicio: cuales tarifas aplican al cafe tostado (gravado,
    exento o excluido, y con que porcentaje segun presentacion) lo define el
    area legal; el modelo no las presume.
    """

    __tablename__ = "taxes"

    id: Mapped[PK]

    code: Mapped[str] = mapped_column(String(20), nullable=False)
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    tax_type: Mapped[str] = mapped_column(String(20), nullable=False)
    rate: Mapped[Percent] = mapped_column(Numeric(9, 6), nullable=False)
    dian_code: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    is_withholding: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="false", default=False
    )

    # -- Relaciones --------------------------------------------------------
    products: Mapped[list["Product"]] = relationship(
        "Product", back_populates="tax", foreign_keys="Product.tax_id"
    )

    __table_args__ = (
        UniqueConstraint("code", name="uq_taxes_code"),
        enum_check("tax_type", TAX_TYPES),
        CheckConstraint("rate >= 0", name="rate_non_negative"),
        validity_check(),
        Index("ix_taxes_tax_type", "tax_type", "valid_to"),
    )

    # -- Utilidades de dominio --------------------------------------------
    @property
    def rate_percent(self) -> float:
        """Tarifa en puntos porcentuales, solo para presentacion."""
        return float(self.rate) * 100

    @property
    def is_zero_rate(self) -> bool:
        return self.rate == 0

    def applies_on(self, day: _dt.date | None = None) -> bool:
        """True si el tributo esta activo y vigente en la fecha dada."""
        return self.is_active and self.covers(day or _dt.date.today())


__all__ = [
    "TAX_TYPES",
    "Tax",
]
