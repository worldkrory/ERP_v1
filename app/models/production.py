"""Modulo Produccion: production_processes, production_orders, process_executions,
production_inputs, production_outputs, production_waste.

Seccion 8 del ERD logico v1.0.

Materializa la regla central del ERD conceptual: el mismo proceso debe poder
ejecutarse hoy por maquila externa y manana con maquinaria propia, sin rediseno.
Eso se logra separando el PROCESO (que se hace, ``production_processes``) de la
EJECUCION (quien lo hizo, cuando y a que costo, ``process_executions``).

El costeo de salida (SPECIFIC_BATCH / WEIGHTED_AVERAGE, seccion 9.4) no vive en
estos modelos: vive en ``app/services/costing.py``.
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
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import (
    PK,
    Base,
    Currency,
    Money,
    Percent,
    Quantity,
    UnitPrice,
    enum_check,
    positive_check,
)
from app.models.mixins import ActiveMixin, AuditMixin, TimestampMixin

if TYPE_CHECKING:
    from app.models.cost import CostRule
    from app.models.party import Party
    from app.models.unit import UnitOfMeasure

# Los cinco procesos iniciales del catalogo (seccion 8.1). Referencia para las
# semillas y para los services; el catalogo es extensible en base de datos.
PRODUCTION_PROCESS_CODES: tuple[str, ...] = (
    "TRILLA",
    "TOSTION",
    "MOLIENDA",
    "EMPAQUE",
    "ETIQUETA",
)

PRODUCTION_ORDER_STATUSES: tuple[str, ...] = (
    "DRAFT",
    "RELEASED",
    "IN_PROGRESS",
    "COMPLETED",
    "CLOSED",
    "CANCELLED",
)

EXECUTOR_TYPES: tuple[str, ...] = ("INTERNAL", "EXTERNAL")

PROCESS_EXECUTION_STATUSES: tuple[str, ...] = (
    "PENDING",
    "SENT",
    "IN_PROGRESS",
    "RECEIVED",
    "DONE",
    "CANCELLED",
)

OUTPUT_KINDS: tuple[str, ...] = ("MAIN", "BYPRODUCT", "REWORK")

WASTE_TYPES: tuple[str, ...] = (
    "MERMA_HUMEDAD",
    "MERMA_PROCESO",
    "PASILLA",
    "CASCARILLA",
    "DEFECTO",
    "DERRAME",
    "CONTAMINACION",
)

WASTE_COST_TREATMENTS: tuple[str, ...] = (
    "ABSORBED_BY_OUTPUT",
    "EXPENSED",
    "ALLOCATED_TO_BYPRODUCT",
)


class ProductionProcess(AuditMixin, ActiveMixin, Base):
    """Catalogo de procesos productivos (seccion 8.1).

    Define QUE se hace, nunca quien lo hace: la identidad del ejecutor vive en
    ``process_executions``. Las cinco filas iniciales son
    ``PRODUCTION_PROCESS_CODES``.

    Invariante de servicio: ``expected_yield_pct`` solo sirve para alertar
    desviaciones de rendimiento. El costo real siempre sale de las cantidades
    registradas, nunca del rendimiento esperado.
    """

    __tablename__ = "production_processes"

    id: Mapped[PK]

    code: Mapped[str] = mapped_column(String(30), nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    # Orden tipico: 10, 20, 30, 40, 50. El orden real de una orden concreta lo
    # fija process_executions.sequence_no.
    default_sequence: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    default_unit_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("units_of_measure.id", ondelete="RESTRICT"),
        nullable=False,
    )
    yields_new_batch: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="false", default=False
    )
    changes_product: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="false", default=False
    )
    expected_yield_pct: Mapped[Optional[Percent]] = mapped_column(
        Numeric(9, 6), nullable=True
    )

    # -- Relaciones --------------------------------------------------------
    executions: Mapped[list["ProcessExecution"]] = relationship(
        "ProcessExecution", back_populates="process"
    )
    cost_rules: Mapped[list["CostRule"]] = relationship(
        "CostRule", back_populates="process", cascade="all, delete-orphan"
    )
    default_unit: Mapped["UnitOfMeasure"] = relationship(
        "UnitOfMeasure", foreign_keys=[default_unit_id]
    )

    __table_args__ = (
        UniqueConstraint("code", name="uq_production_processes_code"),
        # Sin enum_check sobre code: el ERD lista cinco filas INICIALES y el
        # catalogo es extensible en base de datos. PRODUCTION_PROCESS_CODES
        # queda como tupla de referencia para semillas y services.
        CheckConstraint(
            "default_sequence > 0", name="sequence_positive"
        ),
        CheckConstraint(
            "expected_yield_pct IS NULL OR "
            "(expected_yield_pct > 0 AND expected_yield_pct <= 1)",
            name="expected_yield_fraction",
        ),
        Index("ix_production_processes_default_sequence", "default_sequence"),
    )

    # -- Utilidades de dominio --------------------------------------------
    @property
    def display_name(self) -> str:
        return f"{self.name} ({self.code})"

    def yield_deviation(self, actual_pct: decimal.Decimal) -> Optional[decimal.Decimal]:
        """Diferencia entre rendimiento real y esperado, o None si no hay esperado."""
        if self.expected_yield_pct is None:
            return None
        return actual_pct - self.expected_yield_pct


class ProductionOrder(AuditMixin, Base):
    """Orden de produccion: la unidad de costeo del modulo (seccion 8.2).

    Los cinco campos de costo se materializan al cerrar la orden. ``COMPLETED``
    significa que la produccion fisica termino; ``CLOSED`` que el costeo quedo
    cerrado y no admite mas imputaciones (la factura del maquilador llega
    despues).

    Invariante de servicio: el recalculo de ``total_cost``, ``yield_pct`` y
    ``unit_cost``, y el bloqueo de imputaciones sobre ordenes ``CLOSED``, se
    validan en la capa de servicios.
    """

    __tablename__ = "production_orders"

    id: Mapped[PK]

    order_number: Mapped[str] = mapped_column(String(30), nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default="DRAFT", default="DRAFT"
    )
    # FK circular: batch.py apunta de vuelta a production_orders.
    target_product_id: Mapped[Optional[int]] = mapped_column(
        BigInteger,
        ForeignKey("products.id", ondelete="RESTRICT"),
        nullable=True,
    )
    planned_quantity: Mapped[Optional[Quantity]] = mapped_column(
        Numeric(16, 4), nullable=True
    )
    unit_id: Mapped[Optional[int]] = mapped_column(
        BigInteger,
        ForeignKey("units_of_measure.id", ondelete="RESTRICT"),
        nullable=True,
    )
    planned_start_date: Mapped[Optional[_dt.date]] = mapped_column(Date, nullable=True)
    started_at: Mapped[Optional[_dt.datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    completed_at: Mapped[Optional[_dt.datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # -- Descomposicion del costo: cafe / maquila / estructura -------------
    total_input_cost: Mapped[Money] = mapped_column(
        Numeric(16, 2), nullable=False, server_default="0", default=0
    )
    total_process_cost: Mapped[Money] = mapped_column(
        Numeric(16, 2), nullable=False, server_default="0", default=0
    )
    total_overhead_cost: Mapped[Money] = mapped_column(
        Numeric(16, 2), nullable=False, server_default="0", default=0
    )
    total_cost: Mapped[Money] = mapped_column(
        Numeric(16, 2), nullable=False, server_default="0", default=0
    )

    output_quantity_base: Mapped[Quantity] = mapped_column(
        Numeric(16, 4), nullable=False, server_default="0", default=0
    )
    waste_quantity_base: Mapped[Quantity] = mapped_column(
        Numeric(16, 4), nullable=False, server_default="0", default=0
    )
    yield_pct: Mapped[Optional[Percent]] = mapped_column(Numeric(9, 6), nullable=True)
    unit_cost: Mapped[Optional[UnitPrice]] = mapped_column(Numeric(16, 4), nullable=True)
    currency: Mapped[Currency]

    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # -- Relaciones --------------------------------------------------------
    executions: Mapped[list["ProcessExecution"]] = relationship(
        "ProcessExecution",
        back_populates="production_order",
        cascade="all, delete-orphan",
        order_by="ProcessExecution.sequence_no",
    )
    inputs: Mapped[list["ProductionInput"]] = relationship(
        "ProductionInput",
        back_populates="production_order",
        cascade="all, delete-orphan",
    )
    outputs: Mapped[list["ProductionOutput"]] = relationship(
        "ProductionOutput",
        back_populates="production_order",
        cascade="all, delete-orphan",
    )
    waste: Mapped[list["ProductionWaste"]] = relationship(
        "ProductionWaste",
        back_populates="production_order",
        cascade="all, delete-orphan",
    )
    unit: Mapped[Optional["UnitOfMeasure"]] = relationship(
        "UnitOfMeasure", foreign_keys=[unit_id]
    )

    __table_args__ = (
        UniqueConstraint("order_number", name="uq_production_orders_order_number"),
        enum_check("status", PRODUCTION_ORDER_STATUSES),
        CheckConstraint(
            "planned_quantity IS NULL OR planned_quantity > 0",
            name="planned_quantity_positive",
        ),
        positive_check("total_input_cost", allow_zero=True),
        positive_check("total_process_cost", allow_zero=True),
        positive_check("total_overhead_cost", allow_zero=True),
        positive_check("total_cost", allow_zero=True),
        positive_check("output_quantity_base", allow_zero=True),
        positive_check("waste_quantity_base", allow_zero=True),
        CheckConstraint(
            "completed_at IS NULL OR started_at IS NULL OR completed_at >= started_at",
            name="dates_order",
        ),
        Index("ix_production_orders_status", "status"),
        Index("ix_production_orders_dates", "started_at", "completed_at"),
    )

    # -- Utilidades de dominio --------------------------------------------
    @property
    def is_open(self) -> bool:
        """True mientras la orden admite imputaciones de costo."""
        return self.status not in ("CLOSED", "CANCELLED")

    @property
    def is_costing_closed(self) -> bool:
        return self.status == "CLOSED"

    @property
    def cost_breakdown(self) -> dict[str, Optional[decimal.Decimal]]:
        return {
            "input": self.total_input_cost,
            "process": self.total_process_cost,
            "overhead": self.total_overhead_cost,
            "total": self.total_cost,
        }


class ProcessExecution(AuditMixin, Base):
    """Ejecucion concreta de un proceso dentro de una orden (seccion 8.3).

    Es el corazon del diseno de MAQUILA REVERSIBLE. ``executor_type``
    distingue ejecucion propia de maquila: ``EXTERNAL`` exige
    ``executor_party_id`` (el maquilador) e ``INTERNAL`` lo exige NULL. Hoy una
    tostion se registra ``EXTERNAL`` con la party del tostador y una
    ``cost_rule`` de tarifa por libra terminada; el dia que Densa Niebla compre
    tostadora, la misma tostion se registra ``INTERNAL`` con
    ``executor_party_id`` NULL y una ``cost_rule`` interna que suma energia,
    mano de obra y depreciacion. Ninguna tabla cambia, ninguna migracion se
    necesita y los historicos siguen siendo comparables.

    El par ``computed_cost`` / ``actual_cost`` conserva la evidencia cuando el
    maquilador factura distinto a lo pactado.

    Invariante de servicio: la tolerancia del balance de masa (los incrementos
    de humedad pueden hacer que la salida exceda la entrada por poco) y la
    resolucion de la regla de costo aplicable (seccion 9.2) se validan en la
    capa de servicios; si no hay regla se lanza error explicito, nunca costo
    cero.
    """

    __tablename__ = "process_executions"

    id: Mapped[PK]

    production_order_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("production_orders.id", ondelete="CASCADE"),
        nullable=False,
    )
    process_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("production_processes.id", ondelete="RESTRICT"),
        nullable=False,
    )
    sequence_no: Mapped[int] = mapped_column(SmallInteger, nullable=False)

    executor_type: Mapped[str] = mapped_column(String(20), nullable=False)
    executor_party_id: Mapped[Optional[int]] = mapped_column(
        BigInteger, ForeignKey("parties.id", ondelete="RESTRICT"), nullable=True
    )
    location_id: Mapped[Optional[int]] = mapped_column(
        BigInteger,
        ForeignKey("inventory_locations.id", ondelete="RESTRICT"),
        nullable=True,
    )
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default="PENDING", default="PENDING"
    )

    sent_at: Mapped[Optional[_dt.datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    started_at: Mapped[Optional[_dt.datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    finished_at: Mapped[Optional[_dt.datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    received_at: Mapped[Optional[_dt.datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    input_quantity_base: Mapped[Quantity] = mapped_column(
        Numeric(16, 4), nullable=False, server_default="0", default=0
    )
    output_quantity_base: Mapped[Quantity] = mapped_column(
        Numeric(16, 4), nullable=False, server_default="0", default=0
    )
    waste_quantity_base: Mapped[Quantity] = mapped_column(
        Numeric(16, 4), nullable=False, server_default="0", default=0
    )
    yield_pct: Mapped[Optional[Percent]] = mapped_column(Numeric(9, 6), nullable=True)

    # -- Snapshot de costeo: la regla puede cerrarse despues ---------------
    cost_rule_id: Mapped[Optional[int]] = mapped_column(
        BigInteger,
        ForeignKey("cost_rules.id", ondelete="SET NULL"),
        nullable=True,
    )
    cost_unit_id: Mapped[Optional[int]] = mapped_column(
        BigInteger,
        ForeignKey("units_of_measure.id", ondelete="RESTRICT"),
        nullable=True,
    )
    cost_rate: Mapped[Optional[UnitPrice]] = mapped_column(Numeric(16, 4), nullable=True)
    cost_basis: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    chargeable_quantity: Mapped[Optional[Quantity]] = mapped_column(
        Numeric(16, 4), nullable=True
    )
    computed_cost: Mapped[Money] = mapped_column(
        Numeric(16, 2), nullable=False, server_default="0", default=0
    )
    actual_cost: Mapped[Optional[Money]] = mapped_column(Numeric(16, 2), nullable=True)
    currency: Mapped[Currency]

    supplier_document_number: Mapped[Optional[str]] = mapped_column(
        String(40), nullable=True
    )
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # -- Relaciones --------------------------------------------------------
    production_order: Mapped["ProductionOrder"] = relationship(
        "ProductionOrder", back_populates="executions"
    )
    process: Mapped["ProductionProcess"] = relationship(
        "ProductionProcess", back_populates="executions"
    )
    executor_party: Mapped[Optional["Party"]] = relationship(
        "Party", foreign_keys=[executor_party_id]
    )
    cost_rule: Mapped[Optional["CostRule"]] = relationship(
        "CostRule", back_populates="executions", foreign_keys=[cost_rule_id]
    )
    cost_unit: Mapped[Optional["UnitOfMeasure"]] = relationship(
        "UnitOfMeasure", foreign_keys=[cost_unit_id]
    )
    inputs: Mapped[list["ProductionInput"]] = relationship(
        "ProductionInput", back_populates="process_execution"
    )
    outputs: Mapped[list["ProductionOutput"]] = relationship(
        "ProductionOutput", back_populates="process_execution"
    )
    waste: Mapped[list["ProductionWaste"]] = relationship(
        "ProductionWaste", back_populates="process_execution"
    )

    __table_args__ = (
        UniqueConstraint(
            "production_order_id",
            "sequence_no",
            name="uq_process_executions_production_order_id",
        ),
        enum_check("executor_type", EXECUTOR_TYPES),
        enum_check("status", PROCESS_EXECUTION_STATUSES),
        # La clave de la maquila reversible, garantizada en base de datos.
        CheckConstraint(
            "(executor_type = 'EXTERNAL' AND executor_party_id IS NOT NULL) OR "
            "(executor_type = 'INTERNAL' AND executor_party_id IS NULL)",
            name="executor_coherent",
        ),
        CheckConstraint(
            "output_quantity_base + waste_quantity_base <= input_quantity_base",
            name="mass_balance",
        ),
        positive_check("input_quantity_base", allow_zero=True),
        positive_check("output_quantity_base", allow_zero=True),
        positive_check("waste_quantity_base", allow_zero=True),
        positive_check("computed_cost", allow_zero=True),
        CheckConstraint(
            "cost_rate IS NULL OR cost_rate >= 0",
            name="cost_rate_non_negative",
        ),
        CheckConstraint(
            "sequence_no > 0", name="sequence_positive"
        ),
        Index("ix_process_executions_order", "production_order_id", "sequence_no"),
        Index("ix_process_executions_executor", "executor_party_id", "status"),
        Index("ix_process_executions_status", "status"),
    )

    # -- Utilidades de dominio --------------------------------------------
    @property
    def is_outsourced(self) -> bool:
        """True cuando el proceso se ejecuto por maquila externa."""
        return self.executor_type == "EXTERNAL"

    @property
    def is_coffee_outside(self) -> bool:
        """True cuando el cafe esta en poder del maquilador y no ha vuelto."""
        return self.status in ("SENT", "IN_PROGRESS") and self.is_outsourced

    @property
    def effective_cost(self) -> Optional[decimal.Decimal]:
        """Costo real facturado si existe; si no, el calculado por la regla."""
        return self.actual_cost if self.actual_cost is not None else self.computed_cost

    @property
    def cost_variance(self) -> Optional[decimal.Decimal]:
        """Diferencia entre lo facturado y lo pactado. None si no hay factura."""
        if self.actual_cost is None:
            return None
        return self.actual_cost - self.computed_cost


class ProductionInput(TimestampMixin, Base):
    """Consumo de materia prima o insumo en una orden (seccion 8.4).

    ``process_execution_id`` NULL distingue el insumo general de la orden
    (bolsas, etiquetas) del cafe atribuible a una ejecucion concreta.
    ``movement_id`` enlaza con el libro de inventario: todo consumo genera un
    movimiento ``OUT_PRODUCTION`` auditable en ambas direcciones.
    """

    __tablename__ = "production_inputs"

    id: Mapped[PK]

    production_order_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("production_orders.id", ondelete="CASCADE"),
        nullable=False,
    )
    process_execution_id: Mapped[Optional[int]] = mapped_column(
        BigInteger,
        ForeignKey("process_executions.id", ondelete="SET NULL"),
        nullable=True,
    )
    product_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("products.id", ondelete="RESTRICT"),
        nullable=False,
    )
    batch_id: Mapped[Optional[int]] = mapped_column(
        BigInteger,
        ForeignKey("batches.id", ondelete="RESTRICT"),
        nullable=True,
    )
    quantity: Mapped[Quantity] = mapped_column(Numeric(16, 4), nullable=False)
    unit_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("units_of_measure.id", ondelete="RESTRICT"),
        nullable=False,
    )
    quantity_base: Mapped[Quantity] = mapped_column(Numeric(16, 4), nullable=False)
    unit_cost: Mapped[UnitPrice] = mapped_column(Numeric(16, 4), nullable=False)
    total_cost: Mapped[Money] = mapped_column(Numeric(16, 2), nullable=False)
    currency: Mapped[Currency]
    movement_id: Mapped[Optional[int]] = mapped_column(
        BigInteger,
        ForeignKey("inventory_movements.id", ondelete="SET NULL"),
        nullable=True,
    )
    consumed_at: Mapped[_dt.datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        default=func.now(),
    )
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # -- Relaciones --------------------------------------------------------
    production_order: Mapped["ProductionOrder"] = relationship(
        "ProductionOrder", back_populates="inputs"
    )
    process_execution: Mapped[Optional["ProcessExecution"]] = relationship(
        "ProcessExecution", back_populates="inputs"
    )
    unit: Mapped["UnitOfMeasure"] = relationship(
        "UnitOfMeasure", foreign_keys=[unit_id]
    )

    __table_args__ = (
        positive_check("quantity"),
        positive_check("quantity_base"),
        positive_check("unit_cost", allow_zero=True),
        positive_check("total_cost", allow_zero=True),
        Index("ix_production_inputs_order", "production_order_id"),
        Index("ix_production_inputs_execution", "process_execution_id"),
        Index("ix_production_inputs_product", "product_id", "batch_id"),
    )

    # -- Utilidades de dominio --------------------------------------------
    @property
    def is_general_input(self) -> bool:
        """True si el consumo es de la orden y no de una ejecucion concreta."""
        return self.process_execution_id is None


class ProductionOutput(TimestampMixin, Base):
    """Producto obtenido en una orden (seccion 8.5).

    ``output_kind='BYPRODUCT'`` con ``cost_allocation_pct`` resuelve el caso de
    la trilla: excelso (principal) y pasilla (subproducto vendible). La politica
    de reparto elegida se configura en ``app_settings``.

    Invariante de servicio: la suma de ``cost_allocation_pct`` de una orden debe
    cerrar en 1 y el reparto de ``allocated_cost`` se valida en la capa de
    servicios.
    """

    __tablename__ = "production_outputs"

    id: Mapped[PK]

    production_order_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("production_orders.id", ondelete="CASCADE"),
        nullable=False,
    )
    process_execution_id: Mapped[Optional[int]] = mapped_column(
        BigInteger,
        ForeignKey("process_executions.id", ondelete="SET NULL"),
        nullable=True,
    )
    product_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("products.id", ondelete="RESTRICT"),
        nullable=False,
    )
    batch_id: Mapped[Optional[int]] = mapped_column(
        BigInteger,
        ForeignKey("batches.id", ondelete="RESTRICT"),
        nullable=True,
    )
    quantity: Mapped[Quantity] = mapped_column(Numeric(16, 4), nullable=False)
    unit_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("units_of_measure.id", ondelete="RESTRICT"),
        nullable=False,
    )
    quantity_base: Mapped[Quantity] = mapped_column(Numeric(16, 4), nullable=False)
    output_kind: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default="MAIN", default="MAIN"
    )
    cost_allocation_pct: Mapped[Optional[Percent]] = mapped_column(
        Numeric(9, 6), nullable=True
    )
    allocated_cost: Mapped[Money] = mapped_column(
        Numeric(16, 2), nullable=False, server_default="0", default=0
    )
    unit_cost: Mapped[Optional[UnitPrice]] = mapped_column(Numeric(16, 4), nullable=True)
    currency: Mapped[Currency]
    location_id: Mapped[Optional[int]] = mapped_column(
        BigInteger,
        ForeignKey("inventory_locations.id", ondelete="RESTRICT"),
        nullable=True,
    )
    movement_id: Mapped[Optional[int]] = mapped_column(
        BigInteger,
        ForeignKey("inventory_movements.id", ondelete="SET NULL"),
        nullable=True,
    )
    produced_at: Mapped[_dt.datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        default=func.now(),
    )
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # -- Relaciones --------------------------------------------------------
    production_order: Mapped["ProductionOrder"] = relationship(
        "ProductionOrder", back_populates="outputs"
    )
    process_execution: Mapped[Optional["ProcessExecution"]] = relationship(
        "ProcessExecution", back_populates="outputs"
    )
    unit: Mapped["UnitOfMeasure"] = relationship(
        "UnitOfMeasure", foreign_keys=[unit_id]
    )

    __table_args__ = (
        enum_check("output_kind", OUTPUT_KINDS),
        positive_check("quantity"),
        positive_check("quantity_base"),
        positive_check("allocated_cost", allow_zero=True),
        CheckConstraint(
            "cost_allocation_pct IS NULL OR "
            "(cost_allocation_pct >= 0 AND cost_allocation_pct <= 1)",
            name="allocation_fraction",
        ),
        CheckConstraint(
            "unit_cost IS NULL OR unit_cost >= 0",
            name="unit_cost_non_negative",
        ),
        Index("ix_production_outputs_order", "production_order_id"),
        Index("ix_production_outputs_execution", "process_execution_id"),
        Index("ix_production_outputs_product", "product_id", "batch_id"),
    )

    # -- Utilidades de dominio --------------------------------------------
    @property
    def is_main_product(self) -> bool:
        return self.output_kind == "MAIN"


class ProductionWaste(TimestampMixin, Base):
    """Merma generada en una orden (seccion 8.6).

    Responde la pregunta abierta del Avance del ERD en tres niveles:
    ``waste_type`` (que tipo de merma es: cascarilla, humedad, pasilla,
    derrame), ``is_recoverable`` + ``recovered_product_id`` (si tiene mercado,
    genera movimiento ``IN_WASTE_RECOVERY``) y ``cost_treatment`` (si el costo
    lo absorbe el producto bueno, se manda a gasto del periodo o se asigna al
    subproducto).

    El par ``is_expected`` / ``cost_treatment`` permite que el costo unitario
    sea comparable entre lotes y que las perdidas anomalas queden visibles.
    """

    __tablename__ = "production_waste"

    id: Mapped[PK]

    production_order_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("production_orders.id", ondelete="CASCADE"),
        nullable=False,
    )
    process_execution_id: Mapped[Optional[int]] = mapped_column(
        BigInteger,
        ForeignKey("process_executions.id", ondelete="SET NULL"),
        nullable=True,
    )
    product_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("products.id", ondelete="RESTRICT"),
        nullable=False,
    )
    batch_id: Mapped[Optional[int]] = mapped_column(
        BigInteger,
        ForeignKey("batches.id", ondelete="RESTRICT"),
        nullable=True,
    )
    quantity: Mapped[Quantity] = mapped_column(Numeric(16, 4), nullable=False)
    unit_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("units_of_measure.id", ondelete="RESTRICT"),
        nullable=False,
    )
    quantity_base: Mapped[Quantity] = mapped_column(Numeric(16, 4), nullable=False)
    waste_type: Mapped[str] = mapped_column(String(30), nullable=False)
    is_expected: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="true", default=True
    )
    is_recoverable: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="false", default=False
    )
    recovered_product_id: Mapped[Optional[int]] = mapped_column(
        BigInteger,
        ForeignKey("products.id", ondelete="RESTRICT"),
        nullable=True,
    )
    recovered_batch_id: Mapped[Optional[int]] = mapped_column(
        BigInteger,
        ForeignKey("batches.id", ondelete="RESTRICT"),
        nullable=True,
    )
    cost_treatment: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        server_default="ABSORBED_BY_OUTPUT",
        default="ABSORBED_BY_OUTPUT",
    )
    cost_amount: Mapped[Money] = mapped_column(
        Numeric(16, 2), nullable=False, server_default="0", default=0
    )
    movement_id: Mapped[Optional[int]] = mapped_column(
        BigInteger,
        ForeignKey("inventory_movements.id", ondelete="SET NULL"),
        nullable=True,
    )
    occurred_at: Mapped[_dt.datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        default=func.now(),
    )
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # -- Relaciones --------------------------------------------------------
    production_order: Mapped["ProductionOrder"] = relationship(
        "ProductionOrder", back_populates="waste"
    )
    process_execution: Mapped[Optional["ProcessExecution"]] = relationship(
        "ProcessExecution", back_populates="waste"
    )
    unit: Mapped["UnitOfMeasure"] = relationship(
        "UnitOfMeasure", foreign_keys=[unit_id]
    )

    __table_args__ = (
        enum_check("waste_type", WASTE_TYPES),
        enum_check("cost_treatment", WASTE_COST_TREATMENTS),
        positive_check("quantity"),
        positive_check("quantity_base"),
        positive_check("cost_amount", allow_zero=True),
        CheckConstraint(
            "is_recoverable = FALSE OR recovered_product_id IS NOT NULL",
            name="recoverable_requires_product",
        ),
        Index("ix_production_waste_order", "production_order_id"),
        Index("ix_production_waste_execution", "process_execution_id"),
        Index("ix_production_waste_type", "waste_type", "is_expected"),
    )

    # -- Utilidades de dominio --------------------------------------------
    @property
    def is_anomalous(self) -> bool:
        """Merma no esperada: su costo no debe encarecer el producto bueno."""
        return not self.is_expected

    @property
    def goes_to_period_expense(self) -> bool:
        return self.cost_treatment == "EXPENSED"


__all__ = [
    "EXECUTOR_TYPES",
    "OUTPUT_KINDS",
    "PRODUCTION_ORDER_STATUSES",
    "PRODUCTION_PROCESS_CODES",
    "PROCESS_EXECUTION_STATUSES",
    "ProcessExecution",
    "ProductionInput",
    "ProductionOrder",
    "ProductionOutput",
    "ProductionProcess",
    "ProductionWaste",
    "WASTE_COST_TREATMENTS",
    "WASTE_TYPES",
]
