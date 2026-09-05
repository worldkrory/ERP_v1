"""Modulo Unidades: units_of_measure, unit_conversions.

Seccion 4.1 y 4.2 del ERD logico v1.0.

Resuelve el problema operativo de Densa Niebla: se compra en arrobas o cargas,
se produce en libras y se vende en bolsas de 340 g o 500 g. Sin factores
explicitos el costo por libra y el inventario divergen.
"""

from __future__ import annotations

import decimal
from typing import TYPE_CHECKING, Optional

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    ForeignKey,
    Index,
    Numeric,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import PK, Base, Factor, enum_check, positive_check
from app.models.mixins import ActiveMixin, TimestampMixin

if TYPE_CHECKING:
    from app.models.product import Product

UNIT_DIMENSIONS: tuple[str, ...] = ("MASS", "COUNT", "VOLUME", "TIME")


class UnitOfMeasure(TimestampMixin, ActiveMixin, Base):
    """Unidad de medida del catalogo (KG, LB, ARROBA, CARGA, SACO, UN, HORA).

    Seccion 4.1 del ERD. Exactamente una unidad base por dimension, garantizado
    por el indice unico parcial ``uq_uom_one_base_per_dimension``.
    """

    __tablename__ = "units_of_measure"

    id: Mapped[PK]

    code: Mapped[str] = mapped_column(String(15), nullable=False)
    name: Mapped[str] = mapped_column(String(60), nullable=False)
    dimension: Mapped[str] = mapped_column(String(20), nullable=False)
    # Booleano propio de la tabla: no viene de ActiveMixin.
    is_base_for_dimension: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="false", default=False
    )
    # Presentacion, no almacenamiento: el almacenamiento usa NUMERIC(16,4).
    decimal_places: Mapped[int] = mapped_column(
        SmallInteger, nullable=False, server_default="3", default=3
    )
    dian_code: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)

    # -- Relaciones --------------------------------------------------------
    conversions_from: Mapped[list["UnitConversion"]] = relationship(
        "UnitConversion",
        back_populates="from_unit",
        foreign_keys="UnitConversion.from_unit_id",
    )
    conversions_to: Mapped[list["UnitConversion"]] = relationship(
        "UnitConversion",
        back_populates="to_unit",
        foreign_keys="UnitConversion.to_unit_id",
    )
    products_base: Mapped[list["Product"]] = relationship(
        "Product", back_populates="base_unit", foreign_keys="Product.base_unit_id"
    )
    products_sales: Mapped[list["Product"]] = relationship(
        "Product", back_populates="sales_unit", foreign_keys="Product.sales_unit_id"
    )
    products_purchase: Mapped[list["Product"]] = relationship(
        "Product", back_populates="purchase_unit", foreign_keys="Product.purchase_unit_id"
    )

    __table_args__ = (
        UniqueConstraint("code", name="uq_units_of_measure_code"),
        enum_check("dimension", UNIT_DIMENSIONS),
        CheckConstraint(
            "decimal_places >= 0 AND decimal_places <= 6",
            name="decimal_places_range",
        ),
        # Una sola unidad base por dimension (seccion 15, indices parciales).
        Index(
            "uq_uom_one_base_per_dimension",
            "dimension",
            unique=True,
            postgresql_where=text("is_base_for_dimension"),
        ),
        Index("ix_units_of_measure_dimension", "dimension"),
    )

    # -- Utilidades de dominio --------------------------------------------
    @property
    def display_name(self) -> str:
        return f"{self.name} ({self.code})"

    def same_dimension_as(self, other: "UnitOfMeasure") -> bool:
        """True si ambas unidades pertenecen a la misma dimension fisica.

        Condicion necesaria para que exista camino de conversion; el camino en
        si lo resuelve ``app/services/`` (conversion directa especifica, luego
        universal, luego indirecta por la unidad base).
        """
        return self.dimension == other.dimension


class UnitConversion(TimestampMixin, ActiveMixin, Base):
    """Factor de conversion entre dos unidades, opcionalmente por producto.

    Seccion 4.2 del ERD. ``cantidad_to = cantidad_from * factor``.
    ``product_id`` NULL indica conversion universal (1 ARROBA = 12.5 KG);
    con valor indica conversion de empaque (1 UN de bolsa 340 g = 0.34 KG).

    Invariante de servicio: la resolucion de conversiones (directa especifica,
    directa universal, indirecta por la unidad base de la dimension) vive en
    ``app/services/``. Si no existe camino se lanza excepcion: nunca se asume
    factor 1.
    """

    __tablename__ = "unit_conversions"

    id: Mapped[PK]

    from_unit_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("units_of_measure.id", ondelete="RESTRICT"),
        nullable=False,
    )
    to_unit_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("units_of_measure.id", ondelete="RESTRICT"),
        nullable=False,
    )
    factor: Mapped[Factor] = mapped_column(Numeric(20, 10), nullable=False)
    # FK circular: product.py importa de unit.py, de ahi use_alter=True.
    product_id: Mapped[Optional[int]] = mapped_column(
        BigInteger,
        ForeignKey("products.id", ondelete="CASCADE"),
        nullable=True,
    )
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # -- Relaciones --------------------------------------------------------
    from_unit: Mapped["UnitOfMeasure"] = relationship(
        "UnitOfMeasure", back_populates="conversions_from", foreign_keys=[from_unit_id]
    )
    to_unit: Mapped["UnitOfMeasure"] = relationship(
        "UnitOfMeasure", back_populates="conversions_to", foreign_keys=[to_unit_id]
    )
    product: Mapped[Optional["Product"]] = relationship(
        "Product", back_populates="unit_conversions", foreign_keys=[product_id]
    )

    __table_args__ = (
        UniqueConstraint(
            "from_unit_id",
            "to_unit_id",
            "product_id",
            name="uq_unit_conversions_from_unit_id",
        ),
        # En PostgreSQL NULL no colisiona en UNIQUE: el indice parcial cubre
        # el caso de la conversion universal.
        Index(
            "uq_unit_conversions_universal",
            "from_unit_id",
            "to_unit_id",
            unique=True,
            postgresql_where=text("product_id IS NULL"),
        ),
        positive_check("factor"),
        CheckConstraint(
            "from_unit_id <> to_unit_id", name="distinct_units"
        ),
        Index("ix_unit_conversions_product_id", "product_id"),
    )

    # -- Utilidades de dominio --------------------------------------------
    @property
    def is_universal(self) -> bool:
        """True cuando la conversion no depende de un producto concreto."""
        return self.product_id is None

    def convert(self, quantity: decimal.Decimal) -> decimal.Decimal:
        """Aplica este factor a una cantidad expresada en ``from_unit``.

        Solo el paso aritmetico de UN salto directo. La busqueda de camino
        entre unidades sin factor directo es responsabilidad de los services.
        """
        return quantity * self.factor


__all__ = [
    "UNIT_DIMENSIONS",
    "UnitConversion",
    "UnitOfMeasure",
]
