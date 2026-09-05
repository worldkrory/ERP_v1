"""Modulo Costos: cost_categories, cost_rules, cost_entries.

Seccion 9 del ERD logico v1.0.

Generaliza lo que el ERD conceptual llamaba ``PROCESS COST RULE``: una regla de
costo con vigencia para cualquier objeto costeable, y un libro de hechos
economicos (``cost_entries``) con referencia polimorfica al objeto imputado.

Los dos metodos de costeo de la seccion 9.4 (``SPECIFIC_BATCH`` y
``WEIGHTED_AVERAGE``) NO se implementan aqui: la bifurcacion vive en un unico
modulo, ``app/services/costing.py``, con la funcion de entrada
``resolve_outbound_cost(product, batch, location, quantity, at)``. Ningun otro
punto del codigo calcula costo de salida; estos modelos solo almacenan los
snapshots que hacen auditable el resultado.
"""

from __future__ import annotations

import datetime as _dt
import decimal
from typing import TYPE_CHECKING, Optional

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import ExcludeConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import (
    PK,
    Base,
    Currency,
    Money,
    Quantity,
    UnitPrice,
    daterange_expr,
    enum_check,
    positive_check,
    validity_check,
)
from app.models.mixins import ActiveMixin, AuditMixin, ValidityMixin

if TYPE_CHECKING:
    from app.models.party import Party
    from app.models.production import ProcessExecution, ProductionProcess
    from app.models.unit import UnitOfMeasure

COST_NATURES: tuple[str, ...] = ("DIRECT", "INDIRECT")

ALLOCATION_BASES: tuple[str, ...] = ("QUANTITY", "VALUE", "TIME", "MANUAL")

COST_RULE_APPLIES_TO: tuple[str, ...] = (
    "PROCESS",
    "PRODUCT",
    "ORDER",
    "SHIPMENT",
    "SALE",
)

COST_EXECUTOR_TYPES: tuple[str, ...] = ("INTERNAL", "EXTERNAL")

CALCULATION_BASES: tuple[str, ...] = (
    "PER_UNIT_OUTPUT",
    "PER_UNIT_INPUT",
    "FLAT",
    "PER_HOUR",
    "PCT_OF_INPUT_COST",
)

COST_OBJECT_TYPES: tuple[str, ...] = (
    "PRODUCTION_ORDER",
    "PROCESS_EXECUTION",
    "BATCH",
    "PRODUCT",
    "SALE",
    "SALE_ITEM",
    "SHIPMENT",
    "PURCHASE",
    "PARTY",
    "PERIOD",
)


class CostCategory(AuditMixin, ActiveMixin, Base):
    """Categoria de costo, jerarquica (seccion 9.1).

    ``affects_inventory`` decide si el costo entra al valor del inventario o va
    directo al resultado del periodo: el flete de entrada del cafe es costo de
    inventario, el flete de salida al cliente es gasto de venta. La
    clasificacion directo/indirecto no se hardcodea, se configura aqui.

    Invariante de servicio: la jerarquia de ``parent_id`` no debe formar ciclos;
    se valida en la capa de servicios.
    """

    __tablename__ = "cost_categories"

    id: Mapped[PK]

    code: Mapped[str] = mapped_column(String(30), nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    parent_id: Mapped[Optional[int]] = mapped_column(
        BigInteger, ForeignKey("cost_categories.id", ondelete="RESTRICT"), nullable=True
    )
    nature: Mapped[str] = mapped_column(String(20), nullable=False)
    affects_inventory: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="true", default=True
    )
    allocation_basis: Mapped[Optional[str]] = mapped_column(String(25), nullable=True)

    # -- Relaciones --------------------------------------------------------
    parent: Mapped[Optional["CostCategory"]] = relationship(
        "CostCategory", back_populates="children", remote_side="CostCategory.id"
    )
    children: Mapped[list["CostCategory"]] = relationship(
        "CostCategory", back_populates="parent"
    )
    cost_rules: Mapped[list["CostRule"]] = relationship(
        "CostRule", back_populates="cost_category"
    )
    cost_entries: Mapped[list["CostEntry"]] = relationship(
        "CostEntry", back_populates="cost_category"
    )

    __table_args__ = (
        UniqueConstraint("code", name="uq_cost_categories_code"),
        enum_check("nature", COST_NATURES),
        CheckConstraint(
            "allocation_basis IS NULL OR allocation_basis IN "
            "('MANUAL','QUANTITY','TIME','VALUE')",
            name="allocation_basis_valid",
        ),
        Index("ix_cost_categories_parent_id", "parent_id"),
        Index("ix_cost_categories_nature", "nature"),
    )

    # -- Utilidades de dominio --------------------------------------------
    @property
    def is_direct(self) -> bool:
        return self.nature == "DIRECT"

    @property
    def is_period_expense(self) -> bool:
        """True si el costo va al resultado del periodo y no al inventario."""
        return not self.affects_inventory


class CostRule(AuditMixin, ActiveMixin, ValidityMixin, Base):
    """Regla de costo vigente para un objeto costeable (seccion 9.2).

    Cubre tanto la maquila externa (tarifa por libra terminada del maquilador)
    como la ejecucion propia (regla ``INTERNAL`` que suma energia, mano de obra
    y depreciacion): por eso ``executor_type`` y ``executor_party_id`` son
    nulables. ``min_charge`` no es adorno: los maquiladores cobran un minimo por
    tanda y sin el, el costo de las producciones pequenas queda por debajo del
    real.

    La EXCLUDE ``cost_rules_no_overlap`` impide dos reglas solapadas para la
    misma combinacion proceso / ejecutor / producto.

    Invariante de servicio: la resolucion de la regla aplicable (ejecutor
    exacto, luego ``executor_type``, luego generica, y entre candidatas la de
    menor ``priority``) vive en ``app/services/costing.py``. Si no hay regla se
    lanza error explicito: un costo cero silencioso produce margenes falsamente
    buenos que nadie cuestiona.
    """

    __tablename__ = "cost_rules"

    id: Mapped[PK]

    code: Mapped[str] = mapped_column(String(40), nullable=False)
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    cost_category_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("cost_categories.id", ondelete="RESTRICT"), nullable=False
    )
    applies_to: Mapped[str] = mapped_column(String(30), nullable=False)
    process_id: Mapped[Optional[int]] = mapped_column(
        BigInteger,
        ForeignKey("production_processes.id", ondelete="CASCADE"),
        nullable=True,
    )
    product_id: Mapped[Optional[int]] = mapped_column(
        BigInteger,
        ForeignKey("products.id", ondelete="CASCADE"),
        nullable=True,
    )
    executor_type: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    executor_party_id: Mapped[Optional[int]] = mapped_column(
        BigInteger, ForeignKey("parties.id", ondelete="RESTRICT"), nullable=True
    )
    calculation_basis: Mapped[str] = mapped_column(String(30), nullable=False)
    unit_id: Mapped[Optional[int]] = mapped_column(
        BigInteger,
        ForeignKey("units_of_measure.id", ondelete="RESTRICT"),
        nullable=True,
    )
    rate: Mapped[UnitPrice] = mapped_column(Numeric(16, 4), nullable=False)
    currency: Mapped[Currency]
    min_charge: Mapped[Optional[Money]] = mapped_column(Numeric(16, 2), nullable=True)
    max_charge: Mapped[Optional[Money]] = mapped_column(Numeric(16, 2), nullable=True)
    min_quantity: Mapped[Optional[Quantity]] = mapped_column(
        Numeric(16, 4), nullable=True
    )
    priority: Mapped[int] = mapped_column(
        SmallInteger, nullable=False, server_default="100", default=100
    )
    valid_from: Mapped[_dt.date] = mapped_column(Date, nullable=False)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # -- Relaciones --------------------------------------------------------
    cost_category: Mapped["CostCategory"] = relationship(
        "CostCategory", back_populates="cost_rules"
    )
    process: Mapped[Optional["ProductionProcess"]] = relationship(
        "ProductionProcess", back_populates="cost_rules", foreign_keys=[process_id]
    )
    executor_party: Mapped[Optional["Party"]] = relationship(
        "Party", foreign_keys=[executor_party_id]
    )
    unit: Mapped[Optional["UnitOfMeasure"]] = relationship(
        "UnitOfMeasure", foreign_keys=[unit_id]
    )
    executions: Mapped[list["ProcessExecution"]] = relationship(
        "ProcessExecution",
        back_populates="cost_rule",
        foreign_keys="ProcessExecution.cost_rule_id",
    )
    cost_entries: Mapped[list["CostEntry"]] = relationship(
        "CostEntry", back_populates="cost_rule", foreign_keys="CostEntry.cost_rule_id"
    )

    __table_args__ = (
        UniqueConstraint("code", name="uq_cost_rules_code"),
        enum_check("applies_to", COST_RULE_APPLIES_TO),
        enum_check("calculation_basis", CALCULATION_BASES),
        CheckConstraint(
            "executor_type IS NULL OR executor_type IN ('EXTERNAL','INTERNAL')",
            name="executor_type_valid",
        ),
        CheckConstraint(
            "applies_to <> 'PROCESS' OR process_id IS NOT NULL",
            name="process_required",
        ),
        CheckConstraint(
            "calculation_basis IN ('FLAT','PCT_OF_INPUT_COST') OR unit_id IS NOT NULL",
            name="unit_required",
        ),
        CheckConstraint(
            "max_charge IS NULL OR min_charge IS NULL OR max_charge >= min_charge",
            name="charge_range",
        ),
        CheckConstraint(
            "min_quantity IS NULL OR min_quantity > 0",
            name="min_quantity_positive",
        ),
        positive_check("rate", allow_zero=True),
        validity_check(),
        # Sin solapamiento de vigencias para la misma combinacion costeable
        # (seccion 0.5 y punto 11 de las convenciones).
        ExcludeConstraint(
            ("process_id", "="),
            ("executor_party_id", "="),
            ("product_id", "="),
            (text(daterange_expr()), "&&"),
            using="gist",
            name="cost_rules_no_overlap",
        ),
        # Indice critico de la seccion 15: resolucion de costo de maquila.
        Index(
            "ix_cost_rules_lookup", "applies_to", "process_id", "valid_from", "valid_to"
        ),
        Index("ix_cost_rules_executor", "executor_party_id"),
    )

    # -- Utilidades de dominio --------------------------------------------
    @property
    def is_generic(self) -> bool:
        """True si la regla no esta atada a un maquilador concreto."""
        return self.executor_party_id is None

    @property
    def requires_unit(self) -> bool:
        return self.calculation_basis not in ("FLAT", "PCT_OF_INPUT_COST")

    def clamp(self, amount: decimal.Decimal) -> decimal.Decimal:
        """Aplica cargo minimo y maximo a un monto ya calculado.

        Solo el ajuste aritmetico de los topes. El calculo del monto segun
        ``calculation_basis`` es responsabilidad de ``app/services/costing.py``.
        """
        if self.min_charge is not None and amount < self.min_charge:
            amount = self.min_charge
        if self.max_charge is not None and amount > self.max_charge:
            amount = self.max_charge
        return amount


class CostEntry(AuditMixin, Base):
    """Hecho economico: un costo imputado a un objeto del negocio (seccion 9.3).

    ``cost_object_type`` / ``cost_object_id`` es una referencia polimorfica y por
    eso NO lleva FK, igual que en ``inventory_movements``: es la alternativa
    razonable a diez columnas nulables. La integridad del par la garantiza la
    capa de servicios.

    ``is_estimated`` cubre el desfase entre operacion y contabilidad: la tostion
    se costea hoy con la tarifa vigente y la factura del maquilador llega en dos
    semanas. ``accounting_date`` separada de ``incurred_at`` permite imputar al
    periodo correcto un costo registrado tarde. Las correcciones no sobrescriben:
    se registra una entrada con signo contrario apuntada por
    ``reverses_entry_id``.

    Invariante de servicio: la existencia del objeto referenciado por
    ``cost_object_id`` y la coherencia de las reversiones se validan en la capa
    de servicios.
    """

    __tablename__ = "cost_entries"

    id: Mapped[PK]

    cost_category_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("cost_categories.id", ondelete="RESTRICT"), nullable=False
    )
    cost_rule_id: Mapped[Optional[int]] = mapped_column(
        BigInteger, ForeignKey("cost_rules.id", ondelete="SET NULL"), nullable=True
    )
    # Referencia polimorfica: sin FK, a proposito.
    cost_object_type: Mapped[str] = mapped_column(String(30), nullable=False)
    cost_object_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)

    amount: Mapped[Money] = mapped_column(Numeric(16, 2), nullable=False)
    currency: Mapped[Currency]
    quantity: Mapped[Optional[Quantity]] = mapped_column(Numeric(16, 4), nullable=True)
    unit_id: Mapped[Optional[int]] = mapped_column(
        BigInteger,
        ForeignKey("units_of_measure.id", ondelete="RESTRICT"),
        nullable=True,
    )
    unit_rate: Mapped[Optional[UnitPrice]] = mapped_column(Numeric(16, 4), nullable=True)
    calculation_basis: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    party_id: Mapped[Optional[int]] = mapped_column(
        BigInteger, ForeignKey("parties.id", ondelete="RESTRICT"), nullable=True
    )
    incurred_at: Mapped[_dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    accounting_date: Mapped[_dt.date] = mapped_column(Date, nullable=False)
    is_estimated: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="false", default=False
    )
    expense_id: Mapped[Optional[int]] = mapped_column(
        BigInteger,
        ForeignKey("expenses.id", ondelete="SET NULL"),
        nullable=True,
    )
    reverses_entry_id: Mapped[Optional[int]] = mapped_column(
        BigInteger, ForeignKey("cost_entries.id", ondelete="RESTRICT"), nullable=True
    )
    document_reference: Mapped[Optional[str]] = mapped_column(String(60), nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # -- Relaciones --------------------------------------------------------
    cost_category: Mapped["CostCategory"] = relationship(
        "CostCategory", back_populates="cost_entries"
    )
    cost_rule: Mapped[Optional["CostRule"]] = relationship(
        "CostRule", back_populates="cost_entries", foreign_keys=[cost_rule_id]
    )
    party: Mapped[Optional["Party"]] = relationship("Party", foreign_keys=[party_id])
    unit: Mapped[Optional["UnitOfMeasure"]] = relationship(
        "UnitOfMeasure", foreign_keys=[unit_id]
    )
    reverses_entry: Mapped[Optional["CostEntry"]] = relationship(
        "CostEntry", back_populates="reversals", remote_side="CostEntry.id"
    )
    reversals: Mapped[list["CostEntry"]] = relationship(
        "CostEntry", back_populates="reverses_entry"
    )

    __table_args__ = (
        enum_check("cost_object_type", COST_OBJECT_TYPES),
        CheckConstraint(
            "calculation_basis IS NULL OR calculation_basis IN "
            "('FLAT','PCT_OF_INPUT_COST','PER_HOUR','PER_UNIT_INPUT','PER_UNIT_OUTPUT')",
            name="calculation_basis_valid",
        ),
        # Puede ser negativo para correcciones, pero nunca cero.
        CheckConstraint("amount <> 0", name="amount_non_zero"),
        CheckConstraint(
            "cost_object_id IS NOT NULL OR cost_object_type = 'PERIOD'",
            name="object_id_required",
        ),
        CheckConstraint(
            "quantity IS NULL OR quantity > 0",
            name="quantity_positive",
        ),
        CheckConstraint(
            "reverses_entry_id IS NULL OR reverses_entry_id <> id",
            name="no_self_reversal",
        ),
        # Indice critico de la seccion 15: costo total de una orden o lote.
        Index("ix_cost_entries_object", "cost_object_type", "cost_object_id"),
        Index("ix_cost_entries_category", "cost_category_id", "accounting_date"),
        Index("ix_cost_entries_party", "party_id"),
        Index("ix_cost_entries_accounting", "accounting_date"),
    )

    # -- Utilidades de dominio --------------------------------------------
    @property
    def is_reversal(self) -> bool:
        return self.reverses_entry_id is not None

    @property
    def is_credit(self) -> bool:
        """True cuando la entrada resta costo (correccion)."""
        return self.amount < 0


__all__ = [
    "ALLOCATION_BASES",
    "CALCULATION_BASES",
    "COST_EXECUTOR_TYPES",
    "COST_NATURES",
    "COST_OBJECT_TYPES",
    "COST_RULE_APPLIES_TO",
    "CostCategory",
    "CostEntry",
    "CostRule",
]
