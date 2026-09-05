"""Modulo Gastos: expense_categories, expenses.

Seccion 13 del ERD logico v1.0.

La conexion con costos es unidireccional y explicita: si
`expense_categories.is_cost_of_sales = TRUE` el servicio crea el `cost_entry`
correspondiente con `default_cost_category_id`; si es FALSE el gasto solo afecta
el resultado del periodo. Asi se evita contar dos veces un mismo desembolso.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Optional

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    ForeignKey,
    Index,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    desc,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import PK, Base, Currency, Day, Money, enum_check
from app.models.mixins import ActiveMixin, AuditMixin

if TYPE_CHECKING:
    from app.models.cost import CostCategory
    from app.models.party import Party

EXPENSE_NATURES: tuple[str, ...] = (
    "OPERATIONAL",
    "ADMINISTRATIVE",
    "SALES",
    "FINANCIAL",
    "TAX",
    "OTHER",
)

EXPENSE_PAYMENT_STATUSES: tuple[str, ...] = ("UNPAID", "PARTIAL", "PAID")

# Mismo catalogo que payments.method (seccion 10).
EXPENSE_PAYMENT_METHODS: tuple[str, ...] = (
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

EXPENSE_DOCUMENT_TYPES: tuple[str, ...] = (
    "FACTURA",
    "DOCUMENTO_SOPORTE",
    "RECIBO",
    "NOMINA",
    "NINGUNO",
)


class ExpenseCategory(AuditMixin, ActiveMixin, Base):
    """Categoria de gasto, jerarquica. Decide si el desembolso es costo de ventas."""

    __tablename__ = "expense_categories"

    id: Mapped[PK]

    code: Mapped[str] = mapped_column(String(30), nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    # Autorreferencia: arbol de categorias.
    parent_id: Mapped[Optional[int]] = mapped_column(
        BigInteger,
        ForeignKey("expense_categories.id", ondelete="RESTRICT"),
        nullable=True,
    )

    expense_nature: Mapped[str] = mapped_column(String(25), nullable=False)
    # TRUE = el servicio genera cost_entries con la categoria de costo por defecto.
    is_cost_of_sales: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="false", default=False
    )
    default_cost_category_id: Mapped[Optional[int]] = mapped_column(
        BigInteger,
        ForeignKey("cost_categories.id", ondelete="SET NULL"),
        nullable=True,
    )

    # -- Relaciones --------------------------------------------------------
    parent: Mapped[Optional["ExpenseCategory"]] = relationship(
        "ExpenseCategory",
        remote_side="ExpenseCategory.id",
        foreign_keys=[parent_id],
        back_populates="children",
    )
    children: Mapped[list["ExpenseCategory"]] = relationship(
        "ExpenseCategory", foreign_keys=[parent_id], back_populates="parent"
    )
    expenses: Mapped[list["Expense"]] = relationship(
        "Expense", back_populates="category"
    )
    default_cost_category: Mapped[Optional["CostCategory"]] = relationship(
        "CostCategory", foreign_keys=[default_cost_category_id]
    )

    __table_args__ = (
        UniqueConstraint("code", name="uq_expense_categories_code"),
        enum_check("expense_nature", EXPENSE_NATURES),
        CheckConstraint(
            "parent_id IS NULL OR parent_id <> id",
            name="no_self_parent",
        ),
        Index("ix_expense_categories_parent_id", "parent_id"),
    )

    # -- Utilidades de dominio --------------------------------------------
    @property
    def is_root(self) -> bool:
        return self.parent_id is None

    @property
    def full_path(self) -> str:
        """Ruta jerarquica legible, por ejemplo 'OPERACION / FLETES'."""
        if self.parent is None:
            return self.name
        return f"{self.parent.full_path} / {self.name}"


class Expense(AuditMixin, Base):
    """Gasto o desembolso registrado, con su soporte y estado de pago.

    Invariante de servicio: `total` = `subtotal` + `tax_amount` -
    `withholding_amount`; si la categoria es costo de ventas se crea el
    `cost_entry` correspondiente. `is_capitalizable` marca compras de activo
    (una tostadora) cuya depreciacion entra al costo via `cost_rules`.
    """

    __tablename__ = "expenses"

    id: Mapped[PK]

    expense_number: Mapped[str] = mapped_column(String(30), nullable=False)
    category_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("expense_categories.id", ondelete="RESTRICT"), nullable=False
    )
    party_id: Mapped[Optional[int]] = mapped_column(
        BigInteger, ForeignKey("parties.id", ondelete="RESTRICT"), nullable=True
    )

    expense_date: Mapped[Day] = mapped_column(Date, nullable=False)
    accounting_date: Mapped[Day] = mapped_column(Date, nullable=False)
    description: Mapped[str] = mapped_column(String(255), nullable=False)

    subtotal: Mapped[Money] = mapped_column(Numeric(16, 2), nullable=False)
    tax_amount: Mapped[Money] = mapped_column(
        Numeric(16, 2), nullable=False, server_default="0", default=0
    )
    withholding_amount: Mapped[Money] = mapped_column(
        Numeric(16, 2), nullable=False, server_default="0", default=0
    )
    total: Mapped[Money] = mapped_column(Numeric(16, 2), nullable=False)
    currency: Mapped[Currency]

    payment_method: Mapped[Optional[str]] = mapped_column(String(25), nullable=True)
    payment_status: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default="UNPAID", default="UNPAID"
    )

    document_type: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    document_number: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)

    # Compra de activo, no gasto del mes.
    is_capitalizable: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="false", default=False
    )
    is_recurring: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="false", default=False
    )
    attachment_path: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # -- Relaciones --------------------------------------------------------
    category: Mapped["ExpenseCategory"] = relationship(
        "ExpenseCategory", back_populates="expenses"
    )
    party: Mapped[Optional["Party"]] = relationship("Party", foreign_keys=[party_id])

    __table_args__ = (
        UniqueConstraint("expense_number", name="uq_expenses_expense_number"),
        enum_check("payment_status", EXPENSE_PAYMENT_STATUSES),
        CheckConstraint(
            "payment_method IS NULL OR payment_method IN "
            "('CHEQUE','CREDITO','DAVIPLATA','EFECTIVO','NEQUI','OTRO','PSE',"
            "'TARJETA','TRANSFERENCIA')",
            name="payment_method_valid",
        ),
        CheckConstraint(
            "document_type IS NULL OR document_type IN "
            "('DOCUMENTO_SOPORTE','FACTURA','NINGUNO','NOMINA','RECIBO')",
            name="document_type_valid",
        ),
        CheckConstraint("subtotal >= 0", name="subtotal_non_negative"),
        CheckConstraint("tax_amount >= 0", name="tax_amount_non_negative"),
        CheckConstraint(
            "withholding_amount >= 0", name="withholding_non_negative"
        ),
        Index("ix_expenses_category_date", "category_id", "accounting_date"),
        Index("ix_expenses_party", "party_id"),
        Index("ix_expenses_accounting_date", desc("accounting_date")),
    )

    # -- Utilidades de dominio --------------------------------------------
    @property
    def is_paid(self) -> bool:
        return self.payment_status == "PAID"

    @property
    def net_payable(self) -> Money:
        """Monto a desembolsar al tercero, ya descontada la retencion."""
        return self.subtotal + self.tax_amount - self.withholding_amount

    @property
    def affects_cost_of_sales(self) -> bool:
        """True si la categoria manda el gasto al costo del producto."""
        return bool(self.category and self.category.is_cost_of_sales)

    @property
    def has_support(self) -> bool:
        return self.attachment_path is not None


__all__ = [
    "EXPENSE_DOCUMENT_TYPES",
    "EXPENSE_NATURES",
    "EXPENSE_PAYMENT_METHODS",
    "EXPENSE_PAYMENT_STATUSES",
    "Expense",
    "ExpenseCategory",
]
