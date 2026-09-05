"""Modulo Pagos: payments, payment_allocations.

Seccion 10 del ERD logico v1.0 (10.4 y 10.5).

Una sola tabla sirve para cobros y pagos gracias a ``direction``: los pagos a
proveedores, campesinos, maquiladores e intermediarios no duplican estructura.
La aplicacion del dinero a documentos vive en ``payment_allocations`` porque la
relacion pago-venta es N:N en la practica.
"""

from __future__ import annotations

import datetime as _dt
from typing import TYPE_CHECKING, Optional

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    desc,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import PK, Base, Currency, Money, enum_check
from app.models.mixins import AuditMixin, TimestampMixin

if TYPE_CHECKING:
    from app.models.party import Party

PAYMENT_DIRECTIONS: tuple[str, ...] = ("INBOUND", "OUTBOUND")

# NEQUI y DAVIPLATA son explicitos: son canales reales y mayoritarios en la
# venta directa en Colombia y agruparlos en OTRO impediria conciliar.
PAYMENT_METHODS: tuple[str, ...] = (
    "EFECTIVO",
    "TRANSFERENCIA",
    "NEQUI",
    "DAVIPLATA",
    "TARJETA",
    "PSE",
    "CHEQUE",
    "CREDITO",
    "OTRO",
)

PAYMENT_STATUSES: tuple[str, ...] = ("PENDING", "CONFIRMED", "REVERSED")

PAYMENT_TARGET_TYPES: tuple[str, ...] = (
    "SALE",
    "PURCHASE",
    "INVOICE",
    "FEE",
    "EXPENSE",
)


class Payment(AuditMixin, Base):
    """Movimiento de dinero con un tercero: cobro (INBOUND) o pago (OUTBOUND).

    ``allocated_amount`` y ``unallocated_amount`` son totales materializados
    desde ``payment_allocations``; el remanente sin aplicar es un anticipo.

    Invariante de servicio: ``allocated_amount = SUM(allocations.amount)`` y
    ``allocated_amount + unallocated_amount = amount``.
    """

    __tablename__ = "payments"

    id: Mapped[PK]

    payment_number: Mapped[str] = mapped_column(String(30), nullable=False)
    party_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("parties.id", ondelete="RESTRICT"), nullable=False
    )
    direction: Mapped[str] = mapped_column(String(15), nullable=False)
    payment_date: Mapped[_dt.date] = mapped_column(Date, nullable=False)
    method: Mapped[str] = mapped_column(String(25), nullable=False)

    amount: Mapped[Money] = mapped_column(Numeric(16, 2), nullable=False)
    currency: Mapped[Currency]

    allocated_amount: Mapped[Money] = mapped_column(
        Numeric(16, 2), nullable=False, server_default="0", default=0
    )
    unallocated_amount: Mapped[Money] = mapped_column(
        Numeric(16, 2), nullable=False, server_default="0", default=0
    )

    status: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default="CONFIRMED", default="CONFIRMED"
    )

    reference: Mapped[Optional[str]] = mapped_column(String(80), nullable=True)
    bank_account: Mapped[Optional[str]] = mapped_column(String(60), nullable=True)
    receipt_path: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    receipt_url: Mapped[Optional[str]] = mapped_column(String(1024), nullable=True)
    receipt_public_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    receipt_review_status: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default="PENDING", default="PENDING"
    )
    telegram_message_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    receipt_uploaded_at: Mapped[Optional[_dt.datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # -- Relaciones --------------------------------------------------------
    party: Mapped["Party"] = relationship("Party", foreign_keys=[party_id])
    allocations: Mapped[list["PaymentAllocation"]] = relationship(
        "PaymentAllocation", back_populates="payment", cascade="all, delete-orphan"
    )

    __table_args__ = (
        UniqueConstraint("payment_number", name="uq_payments_payment_number"),
        enum_check("direction", PAYMENT_DIRECTIONS),
        enum_check("method", PAYMENT_METHODS),
        enum_check("status", PAYMENT_STATUSES),
        CheckConstraint("amount > 0", name="amount_positive"),
        CheckConstraint(
            "allocated_amount >= 0", name="allocated_non_negative"
        ),
        CheckConstraint(
            "unallocated_amount >= 0", name="unallocated_non_negative"
        ),
        # De filtrado frecuente (seccion 15).
        Index("ix_payments_party", "party_id", desc("payment_date")),
        Index("ix_payments_status", "status"),
    )

    # -- Utilidades de dominio --------------------------------------------
    @property
    def is_inbound(self) -> bool:
        return self.direction == "INBOUND"

    @property
    def is_reversed(self) -> bool:
        return self.status == "REVERSED"

    @property
    def is_advance(self) -> bool:
        """Anticipo: dinero confirmado con saldo sin aplicar a documentos."""
        return self.status == "CONFIRMED" and self.unallocated_amount > 0

    @property
    def available_amount(self) -> Money:
        """Monto que aun se puede aplicar a documentos."""
        return self.amount - self.allocated_amount

    @property
    def is_fully_allocated(self) -> bool:
        return self.available_amount <= 0


class PaymentAllocation(TimestampMixin, Base):
    """Aplicacion de un pago a un documento concreto (venta, compra, factura...).

    ``target_type`` + ``target_id`` es una referencia polimorfica: NO lleva FK
    sobre ``target_id`` porque el documento destino puede estar en varias
    tablas. La integridad la garantiza la capa de servicios.

    Invariante de servicio: ``SUM(payment_allocations.amount) <=
    payments.amount``; no se implementa como CHECK porque agrega filas de la
    propia tabla contra la cabecera.
    """

    __tablename__ = "payment_allocations"

    id: Mapped[PK]

    payment_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("payments.id", ondelete="CASCADE"), nullable=False
    )
    # Referencia polimorfica: sin ForeignKey a proposito.
    target_type: Mapped[str] = mapped_column(String(20), nullable=False)
    target_id: Mapped[int] = mapped_column(BigInteger, nullable=False)

    amount: Mapped[Money] = mapped_column(Numeric(16, 2), nullable=False)
    allocated_at: Mapped[_dt.datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        default=func.now(),
    )
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # -- Relaciones --------------------------------------------------------
    payment: Mapped["Payment"] = relationship("Payment", back_populates="allocations")

    __table_args__ = (
        UniqueConstraint(
            "payment_id",
            "target_type",
            "target_id",
            name="uq_payment_allocations_payment_id",
        ),
        enum_check("target_type", PAYMENT_TARGET_TYPES),
        CheckConstraint("amount > 0", name="amount_positive"),
        Index("ix_payment_allocations_target", "target_type", "target_id"),
    )

    # -- Utilidades de dominio --------------------------------------------
    @property
    def applies_to_sale(self) -> bool:
        return self.target_type == "SALE"

    @property
    def target_ref(self) -> str:
        """Etiqueta legible de la referencia polimorfica."""
        return f"{self.target_type}:{self.target_id}"


__all__ = [
    "PAYMENT_DIRECTIONS",
    "PAYMENT_METHODS",
    "PAYMENT_STATUSES",
    "PAYMENT_TARGET_TYPES",
    "Payment",
    "PaymentAllocation",
]
