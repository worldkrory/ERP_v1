"""Modulo Comisiones de intermediarios: intermediary_fee_rules, intermediary_fee_entries.

Seccion 5 (5.4 y 5.5) del ERD logico v1.0.

La configuracion (la regla) y el hecho economico (el devengo) viven en tablas
distintas a proposito: la regla puede cambiar el ano entrante y las comisiones
ya devengadas deben seguir siendo auditables con la regla que se les aplico. De
ahi los snapshots ``calculation_basis`` y ``rule_value`` en las entradas.
"""

from __future__ import annotations

import datetime as _dt
from typing import TYPE_CHECKING, Optional

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    SmallInteger,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import (
    PK,
    Base,
    Currency,
    Money,
    UnitPrice,
    enum_check,
    validity_check,
)
from app.models.mixins import ActiveMixin, AuditMixin, ValidityMixin

if TYPE_CHECKING:
    from app.models.expense import Expense
    from app.models.party import Party
    from app.models.product import Product, ProductCategory
    from app.models.sale import Sale
    from app.models.uom import UnitOfMeasure

FEE_CALCULATION_BASES: tuple[str, ...] = (
    "PCT_OF_SALE_TOTAL",
    "PCT_OF_MARGIN",
    "PER_UNIT",
    "FLAT_PER_SALE",
)

FEE_ENTRY_STATUSES: tuple[str, ...] = ("ACCRUED", "APPROVED", "PAID", "CANCELLED")


class IntermediaryFeeRule(AuditMixin, ActiveMixin, ValidityMixin, Base):
    """Regla de comision de un intermediario (seccion 5.4 del ERD).

    ``PCT_OF_MARGIN`` existe porque comisionar sobre el total de la venta y
    comisionar sobre el margen son negocios distintos, y en cafe la diferencia
    decide si la venta es rentable.

    Invariante de servicio: la party referenciada debe tener el rol
    ``INTERMEDIARY`` vigente; se valida en la capa de servicios.
    """

    __tablename__ = "intermediary_fee_rules"

    id: Mapped[PK]

    party_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("parties.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    calculation_basis: Mapped[str] = mapped_column(String(25), nullable=False)
    value: Mapped[UnitPrice] = mapped_column(Numeric(16, 4), nullable=False)

    unit_id: Mapped[Optional[int]] = mapped_column(
        BigInteger,
        ForeignKey("units_of_measure.id", ondelete="RESTRICT"),
        nullable=True,
    )
    product_id: Mapped[Optional[int]] = mapped_column(
        BigInteger,
        ForeignKey("products.id", ondelete="RESTRICT"),
        nullable=True,
    )
    category_id: Mapped[Optional[int]] = mapped_column(
        BigInteger,
        ForeignKey("product_categories.id", ondelete="RESTRICT"),
        nullable=True,
    )

    min_fee_amount: Mapped[Optional[Money]] = mapped_column(Numeric(16, 2), nullable=True)
    max_fee_amount: Mapped[Optional[Money]] = mapped_column(Numeric(16, 2), nullable=True)

    priority: Mapped[int] = mapped_column(
        SmallInteger, nullable=False, server_default="100", default=100
    )

    # -- Relaciones --------------------------------------------------------
    party: Mapped["Party"] = relationship("Party", foreign_keys=[party_id])
    unit: Mapped[Optional["UnitOfMeasure"]] = relationship(
        "UnitOfMeasure", foreign_keys=[unit_id]
    )
    product: Mapped[Optional["Product"]] = relationship(
        "Product", foreign_keys=[product_id]
    )
    category: Mapped[Optional["ProductCategory"]] = relationship(
        "ProductCategory", foreign_keys=[category_id]
    )
    entries: Mapped[list["IntermediaryFeeEntry"]] = relationship(
        "IntermediaryFeeEntry", back_populates="rule"
    )

    __table_args__ = (
        enum_check("calculation_basis", FEE_CALCULATION_BASES),
        CheckConstraint("value >= 0", name="value_non_negative"),
        CheckConstraint(
            "calculation_basis <> 'PER_UNIT' OR unit_id IS NOT NULL",
            name="per_unit_requires_unit",
        ),
        CheckConstraint(
            "max_fee_amount IS NULL OR min_fee_amount IS NULL "
            "OR max_fee_amount >= min_fee_amount",
            name="fee_amount_range",
        ),
        CheckConstraint(
            "calculation_basis NOT LIKE 'PCT%' OR value <= 1",
            name="pct_fraction",
        ),
        validity_check(),
        Index(
            "ix_intermediary_fee_rules_party_id", "party_id", "priority", "valid_to"
        ),
    )

    @property
    def is_percentage(self) -> bool:
        return self.calculation_basis.startswith("PCT")


class IntermediaryFeeEntry(AuditMixin, Base):
    """Devengo de comision de un intermediario sobre una venta (seccion 5.5).

    ``calculation_basis`` y ``rule_value`` son snapshots deliberados de la regla
    aplicada; ``expense_id`` vincula el pago real cuando se liquida.

    Invariante de servicio: solo las entradas en estado APPROVED se liquidan, y
    ``settled_at`` se llena al pasar a PAID.
    """

    __tablename__ = "intermediary_fee_entries"

    id: Mapped[PK]

    party_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("parties.id", ondelete="RESTRICT"), nullable=False
    )
    sale_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("sales.id", ondelete="RESTRICT"),
        nullable=False,
    )
    rule_id: Mapped[Optional[int]] = mapped_column(
        BigInteger,
        ForeignKey("intermediary_fee_rules.id", ondelete="SET NULL"),
        nullable=True,
    )

    # -- Snapshots de la regla aplicada ------------------------------------
    calculation_basis: Mapped[str] = mapped_column(String(25), nullable=False)
    rule_value: Mapped[UnitPrice] = mapped_column(Numeric(16, 4), nullable=False)

    base_amount: Mapped[Money] = mapped_column(Numeric(16, 2), nullable=False)
    fee_amount: Mapped[Money] = mapped_column(Numeric(16, 2), nullable=False)
    currency: Mapped[Currency]

    status: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default="ACCRUED", default="ACCRUED"
    )
    accrued_at: Mapped[_dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), default=func.now()
    )
    settled_at: Mapped[Optional[_dt.datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    expense_id: Mapped[Optional[int]] = mapped_column(
        BigInteger,
        ForeignKey("expenses.id", ondelete="SET NULL"),
        nullable=True,
    )
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # -- Relaciones --------------------------------------------------------
    party: Mapped["Party"] = relationship("Party", foreign_keys=[party_id])
    sale: Mapped["Sale"] = relationship("Sale", foreign_keys=[sale_id])
    rule: Mapped[Optional["IntermediaryFeeRule"]] = relationship(
        "IntermediaryFeeRule", back_populates="entries", foreign_keys=[rule_id]
    )
    expense: Mapped[Optional["Expense"]] = relationship(
        "Expense", foreign_keys=[expense_id]
    )

    __table_args__ = (
        enum_check("calculation_basis", FEE_CALCULATION_BASES),
        enum_check("status", FEE_ENTRY_STATUSES),
        CheckConstraint(
            "fee_amount >= 0", name="fee_amount_non_negative"
        ),
        CheckConstraint(
            "settled_at IS NULL OR settled_at >= accrued_at",
            name="settled_after_accrued",
        ),
        Index("ix_ife_party_status", "party_id", "status"),
        Index("ix_ife_sale", "sale_id"),
    )

    @property
    def is_settled(self) -> bool:
        return self.status == "PAID"

    @property
    def is_open(self) -> bool:
        return self.status in ("ACCRUED", "APPROVED")


__all__ = [
    "FEE_CALCULATION_BASES",
    "FEE_ENTRY_STATUSES",
    "IntermediaryFeeEntry",
    "IntermediaryFeeRule",
]
