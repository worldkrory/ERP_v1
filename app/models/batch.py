"""Modulo Lotes: batches, batch_lineage.

Seccion 7.2 y 7.3 del ERD logico v1.0.

El lote es la unidad de trazabilidad del cafe: identifica de que finca viene,
que costo tiene y en que estado esta. ``batch_lineage`` modela la relacion N:N
entre lotes de entrada y lotes de salida de una transformacion: una tostion
puede mezclar tres lotes de verde y un lote de verde puede alimentar varias
tostiones.
"""

from __future__ import annotations

import datetime as _dt
from typing import TYPE_CHECKING, Any, Optional

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Date,
    ForeignKey,
    Index,
    Numeric,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import (
    PK,
    Base,
    Currency,
    Percent,
    Quantity,
    UnitPrice,
    enum_check,
    positive_check,
)
from app.models.mixins import AuditMixin, TimestampMixin

if TYPE_CHECKING:
    from app.models.party import Address, Party
    from app.models.product import Product
    from app.models.production import ProductionOrder
    from app.models.purchase import PurchaseItem
    from app.models.uom import UnitOfMeasure

BATCH_TYPES: tuple[str, ...] = ("PURCHASED", "PRODUCED", "ADJUSTED")

BATCH_STATUSES: tuple[str, ...] = ("ACTIVE", "DEPLETED", "BLOCKED", "EXPIRED")

HARVEST_PERIODS: tuple[str, ...] = ("PRINCIPAL", "TRAVIESA")


class Batch(AuditMixin, Base):
    """Lote de producto con trazabilidad de origen y costo (seccion 7.2).

    ``status = 'BLOCKED'`` retiene un lote con problema de calidad sin borrarlo
    ni alterar el inventario.

    Invariante de servicio: ``status = 'DEPLETED'`` es un dato derivado (saldo
    cero) y debe poder recalcularse desde ``inventory_movements``.
    """

    __tablename__ = "batches"

    id: Mapped[PK]

    batch_code: Mapped[str] = mapped_column(String(40), nullable=False)
    product_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("products.id", ondelete="RESTRICT"), nullable=False
    )
    batch_type: Mapped[str] = mapped_column(String(25), nullable=False)

    # -- Origen. Snapshots: la finca puede cambiar de nombre o de dueno.
    origin_party_id: Mapped[Optional[int]] = mapped_column(
        BigInteger, ForeignKey("parties.id", ondelete="RESTRICT"), nullable=True
    )
    origin_address_id: Mapped[Optional[int]] = mapped_column(
        BigInteger, ForeignKey("addresses.id", ondelete="SET NULL"), nullable=True
    )
    farm_name: Mapped[Optional[str]] = mapped_column(String(150), nullable=True)
    municipality_name: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    harvest_year: Mapped[Optional[int]] = mapped_column(SmallInteger, nullable=True)
    harvest_period: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)

    # -- Documento que origino el lote.
    production_order_id: Mapped[Optional[int]] = mapped_column(
        BigInteger,
        ForeignKey("production_orders.id", ondelete="SET NULL"),
        nullable=True,
    )
    # Dependencia circular con purchase_items: esa tabla apunta de vuelta con
    # purchase_items.batch_id, por eso use_alter=True en ambas FK.
    purchase_item_id: Mapped[Optional[int]] = mapped_column(
        BigInteger,
        ForeignKey("purchase_items.id", ondelete="SET NULL", use_alter=True),
        nullable=True,
    )

    initial_quantity: Mapped[Quantity] = mapped_column(Numeric(16, 4), nullable=False)
    unit_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("units_of_measure.id", ondelete="RESTRICT"),
        nullable=False,
    )
    # Base del costeo SPECIFIC_BATCH (seccion 9).
    unit_cost: Mapped[UnitPrice] = mapped_column(Numeric(16, 4), nullable=False)
    currency: Mapped[Currency]

    # -- Calidad.
    humidity_pct: Mapped[Optional[Any]] = mapped_column(Numeric(5, 2), nullable=True)
    defect_pct: Mapped[Optional[Any]] = mapped_column(Numeric(5, 2), nullable=True)
    cupping_score: Mapped[Optional[Any]] = mapped_column(Numeric(5, 2), nullable=True)

    received_date: Mapped[Optional[_dt.date]] = mapped_column(Date, nullable=True)
    production_date: Mapped[Optional[_dt.date]] = mapped_column(Date, nullable=True)
    expiry_date: Mapped[Optional[_dt.date]] = mapped_column(Date, nullable=True)

    status: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default="ACTIVE", default="ACTIVE"
    )
    quality_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # -- Relaciones --------------------------------------------------------
    # Linea de compra que origino el lote (batches.purchase_item_id).
    purchase_item: Mapped[Optional["PurchaseItem"]] = relationship(
        "PurchaseItem",
        back_populates="origin_batches",
        foreign_keys=[purchase_item_id],
    )
    # Lado inverso de purchase_items.batch_id: lineas que apuntan a este lote.
    source_purchase_items: Mapped[list["PurchaseItem"]] = relationship(
        "PurchaseItem",
        back_populates="batch",
        foreign_keys="PurchaseItem.batch_id",
    )

    # Linaje: filas donde este lote es el hijo (sus padres) y filas donde este
    # lote es el padre (sus hijos). foreign_keys explicito porque ambas FK
    # apuntan a batches.
    parent_links: Mapped[list["BatchLineage"]] = relationship(
        "BatchLineage",
        back_populates="child_batch",
        foreign_keys="BatchLineage.child_batch_id",
        cascade="all, delete-orphan",
    )
    child_links: Mapped[list["BatchLineage"]] = relationship(
        "BatchLineage",
        back_populates="parent_batch",
        foreign_keys="BatchLineage.parent_batch_id",
    )
    # Vistas N:N a traves de la tabla de linaje.
    parent_batches: Mapped[list["Batch"]] = relationship(
        "Batch",
        secondary="batch_lineage",
        primaryjoin="Batch.id == BatchLineage.child_batch_id",
        secondaryjoin="Batch.id == BatchLineage.parent_batch_id",
        viewonly=True,
    )
    child_batches: Mapped[list["Batch"]] = relationship(
        "Batch",
        secondary="batch_lineage",
        primaryjoin="Batch.id == BatchLineage.parent_batch_id",
        secondaryjoin="Batch.id == BatchLineage.child_batch_id",
        viewonly=True,
    )

    product: Mapped["Product"] = relationship("Product", foreign_keys=[product_id])
    unit: Mapped["UnitOfMeasure"] = relationship(
        "UnitOfMeasure", foreign_keys=[unit_id]
    )
    origin_party: Mapped[Optional["Party"]] = relationship(
        "Party", foreign_keys=[origin_party_id]
    )
    origin_address: Mapped[Optional["Address"]] = relationship(
        "Address", foreign_keys=[origin_address_id]
    )
    production_order: Mapped[Optional["ProductionOrder"]] = relationship(
        "ProductionOrder", foreign_keys=[production_order_id]
    )

    __table_args__ = (
        UniqueConstraint("batch_code", name="uq_batches_batch_code"),
        enum_check("batch_type", BATCH_TYPES),
        enum_check("status", BATCH_STATUSES),
        CheckConstraint(
            "harvest_period IS NULL OR harvest_period IN ('PRINCIPAL','TRAVIESA')",
            name="harvest_period_valid",
        ),
        positive_check("initial_quantity"),
        CheckConstraint("unit_cost >= 0", name="unit_cost_non_negative"),
        CheckConstraint(
            "humidity_pct IS NULL OR (humidity_pct >= 0 AND humidity_pct <= 100)",
            name="humidity_pct_range",
        ),
        CheckConstraint(
            "defect_pct IS NULL OR (defect_pct >= 0 AND defect_pct <= 100)",
            name="defect_pct_range",
        ),
        CheckConstraint(
            "batch_type <> 'PRODUCED' OR production_order_id IS NOT NULL",
            name="produced_requires_order",
        ),
        CheckConstraint(
            "expiry_date IS NULL OR production_date IS NULL "
            "OR expiry_date >= production_date",
            name="expiry_after_production",
        ),
        Index("ix_batches_product", "product_id", "status"),
        Index("ix_batches_origin_party", "origin_party_id"),
        Index("ix_batches_harvest_year", "harvest_year"),
    )

    # -- Utilidades de dominio --------------------------------------------
    @property
    def is_available(self) -> bool:
        """True si el lote puede consumirse o venderse."""
        return self.status == "ACTIVE"

    @property
    def is_blend(self) -> bool:
        """True si el lote proviene de mas de un lote padre."""
        return len(self.parent_links) > 1

    @property
    def initial_value(self) -> Any:
        return self.initial_quantity * self.unit_cost

    def is_expired(self, on: _dt.date | None = None) -> bool:
        if self.expiry_date is None:
            return False
        return (on or _dt.date.today()) > self.expiry_date


class BatchLineage(TimestampMixin, Base):
    """Arista de trazabilidad entre un lote padre y un lote hijo (seccion 7.3).

    ``contribution_pct`` sustenta la trazabilidad hacia atras: de que fincas
    viene una bolsa vendida y en que proporcion.

    Invariante de servicio: la suma de ``contribution_pct`` de los padres de un
    mismo hijo debe ser 1.
    """

    __tablename__ = "batch_lineage"

    id: Mapped[PK]

    child_batch_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("batches.id", ondelete="CASCADE"), nullable=False
    )
    parent_batch_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("batches.id", ondelete="RESTRICT"), nullable=False
    )
    quantity_consumed: Mapped[Quantity] = mapped_column(Numeric(16, 4), nullable=False)
    unit_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("units_of_measure.id", ondelete="RESTRICT"),
        nullable=False,
    )
    contribution_pct: Mapped[Optional[Percent]] = mapped_column(
        Numeric(9, 6), nullable=True
    )
    production_order_id: Mapped[Optional[int]] = mapped_column(
        BigInteger,
        ForeignKey("production_orders.id", ondelete="SET NULL"),
        nullable=True,
    )

    # -- Relaciones --------------------------------------------------------
    # N:N autorreferencial: ambas FK apuntan a batches, por eso foreign_keys y
    # primaryjoin explicitos en los dos lados.
    child_batch: Mapped["Batch"] = relationship(
        "Batch",
        back_populates="parent_links",
        foreign_keys=[child_batch_id],
        primaryjoin="BatchLineage.child_batch_id == Batch.id",
    )
    parent_batch: Mapped["Batch"] = relationship(
        "Batch",
        back_populates="child_links",
        foreign_keys=[parent_batch_id],
        primaryjoin="BatchLineage.parent_batch_id == Batch.id",
    )
    unit: Mapped["UnitOfMeasure"] = relationship(
        "UnitOfMeasure", foreign_keys=[unit_id]
    )
    production_order: Mapped[Optional["ProductionOrder"]] = relationship(
        "ProductionOrder", foreign_keys=[production_order_id]
    )

    __table_args__ = (
        UniqueConstraint(
            "child_batch_id", "parent_batch_id", name="uq_batch_lineage_child_batch_id"
        ),
        CheckConstraint(
            "child_batch_id <> parent_batch_id", name="no_self_parent"
        ),
        positive_check("quantity_consumed"),
        CheckConstraint(
            "contribution_pct IS NULL "
            "OR (contribution_pct >= 0 AND contribution_pct <= 1)",
            name="contribution_pct_fraction",
        ),
        Index("ix_batch_lineage_parent_batch_id", "parent_batch_id"),
        Index("ix_batch_lineage_child_batch_id", "child_batch_id"),
    )


__all__ = [
    "BATCH_STATUSES",
    "BATCH_TYPES",
    "Batch",
    "BatchLineage",
    "HARVEST_PERIODS",
]
