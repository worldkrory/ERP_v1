"""Modulo Inventario: inventory_locations, inventory_movements, inventory_balances.

Secciones 7.1, 7.4 y 7.5 del ERD logico v1.0.

El inventario es un libro historico de movimientos, no una cifra:
``inventory_movements`` es append-only (nunca UPDATE ni DELETE) y
``inventory_balances`` es una tabla derivada, reconstruible, que existe solo por
rendimiento.
"""

from __future__ import annotations

import datetime as _dt
from typing import TYPE_CHECKING, Optional

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import (
    PK,
    Base,
    Currency,
    Money,
    Quantity,
    UnitPrice,
    enum_check,
    positive_check,
)
from app.models.mixins import ActiveMixin, AuditMixin

if TYPE_CHECKING:
    from app.models.batch import Batch
    from app.models.party import Address, Party
    from app.models.product import Product
    from app.models.uom import UnitOfMeasure
    from app.models.user import User

# El tipo PROCESSOR modela al maquilador: el cafe enviado al trillador sigue
# siendo inventario propio aunque no este en bodega. SCRAP es la contrapartida
# de la merma no recuperable.
LOCATION_TYPES: tuple[str, ...] = (
    "WAREHOUSE",
    "PROCESSOR",
    "IN_TRANSIT",
    "CONSIGNMENT",
    "CUSTOMER",
    "SCRAP",
    "VIRTUAL",
)

# Catalogo cerrado de la seccion 7.4: 13 tipos de movimiento.
MOVEMENT_TYPES: tuple[str, ...] = (
    "IN_PURCHASE",
    "IN_PRODUCTION",
    "IN_SALE_RETURN",
    "IN_ADJUSTMENT",
    "IN_TRANSFER",
    "IN_WASTE_RECOVERY",
    "OUT_SALE",
    "OUT_PRODUCTION",
    "OUT_WASTE",
    "OUT_ADJUSTMENT",
    "OUT_TRANSFER",
    "OUT_SAMPLE",
    "OUT_PURCHASE_RETURN",
)

# direction obligatorio por tipo: +1 entrada, -1 salida.
MOVEMENT_TYPES_IN: tuple[str, ...] = tuple(
    t for t in MOVEMENT_TYPES if t.startswith("IN_")
)
MOVEMENT_TYPES_OUT: tuple[str, ...] = tuple(
    t for t in MOVEMENT_TYPES if t.startswith("OUT_")
)

MOVEMENT_REFERENCE_TYPES: tuple[str, ...] = (
    "PURCHASE_ITEM",
    "SALE_ITEM_BATCH",
    "PRODUCTION_INPUT",
    "PRODUCTION_OUTPUT",
    "PRODUCTION_WASTE",
    "SHIPMENT_ITEM",
    "ADJUSTMENT",
    "TRANSFER",
    "COUNT",
)

MOVEMENT_REASON_CODES: tuple[str, ...] = (
    "CONTEO_FISICO",
    "DANO",
    "ROBO",
    "ERROR_REGISTRO",
    "MUESTRA",
    "OBSEQUIO",
)


def _sql_list(values: tuple[str, ...]) -> str:
    """Lista SQL de literales, ordenada para que el CHECK sea estable."""
    return ", ".join(f"'{v}'" for v in sorted(values))


class InventoryLocation(AuditMixin, ActiveMixin, Base):
    """Ubicacion de inventario: bodega, maquilador, consignacion, transito.

    Seccion 7.1. Modelar al maquilador como ubicacion ``PROCESSOR`` permite
    saber cuanto cafe hay en poder de terceros y cuadrar el inventario fisico de
    la bodega sin que el cafe en maquila lo descuadre.
    """

    __tablename__ = "inventory_locations"

    id: Mapped[PK]

    code: Mapped[str] = mapped_column(String(30), nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    location_type: Mapped[str] = mapped_column(String(30), nullable=False)

    # Requerido para PROCESSOR y CONSIGNMENT: el tercero que la custodia.
    party_id: Mapped[Optional[int]] = mapped_column(
        BigInteger, ForeignKey("parties.id", ondelete="RESTRICT"), nullable=True
    )
    address_id: Mapped[Optional[int]] = mapped_column(
        BigInteger, ForeignKey("addresses.id", ondelete="SET NULL"), nullable=True
    )

    allows_negative_stock: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="false", default=False
    )
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # -- Relaciones --------------------------------------------------------
    movements: Mapped[list["InventoryMovement"]] = relationship(
        "InventoryMovement",
        back_populates="location",
        foreign_keys="InventoryMovement.location_id",
    )
    balances: Mapped[list["InventoryBalance"]] = relationship(
        "InventoryBalance",
        back_populates="location",
        foreign_keys="InventoryBalance.location_id",
        cascade="all, delete-orphan",
    )
    party: Mapped[Optional["Party"]] = relationship("Party", foreign_keys=[party_id])
    address: Mapped[Optional["Address"]] = relationship(
        "Address", foreign_keys=[address_id]
    )

    __table_args__ = (
        UniqueConstraint("code", name="uq_inventory_locations_code"),
        enum_check("location_type", LOCATION_TYPES),
        CheckConstraint(
            "location_type NOT IN ('PROCESSOR','CONSIGNMENT') OR party_id IS NOT NULL",
            name="third_party_requires_party",
        ),
        Index("ix_inventory_locations_location_type", "location_type"),
        Index("ix_inventory_locations_party_id", "party_id"),
    )

    # -- Utilidades de dominio --------------------------------------------
    @property
    def is_third_party(self) -> bool:
        """True si el inventario esta fisicamente en poder de un tercero."""
        return self.location_type in ("PROCESSOR", "CONSIGNMENT", "CUSTOMER")

    @property
    def display_name(self) -> str:
        return f"{self.code} - {self.name}"


class InventoryMovement(Base):
    """Movimiento de inventario. Tabla central y **append-only** (seccion 7.4).

    Nunca se hace UPDATE ni DELETE: un error se corrige con un movimiento de
    reversa que apunta al original mediante ``reverses_movement_id``. Por eso no
    lleva ``updated_at`` ni AuditMixin, solo ``created_at`` y ``created_by_id``.

    ``quantity`` es siempre positiva y el signo vive en ``direction``, de modo
    que los saldos se calculan como ``SUM(quantity_base * direction)``.

    ``reference_type`` + ``reference_id`` es una referencia polimorfica sin FK
    real: la integridad la garantiza la capa de servicios, unica autorizada a
    crear movimientos.

    Invariante de servicio: los traslados (``%TRANSFER%``) siempre se crean en
    pareja y deben tener ``counterpart_movement_id``.
    """

    __tablename__ = "inventory_movements"

    id: Mapped[PK]

    movement_type: Mapped[str] = mapped_column(String(35), nullable=False)
    direction: Mapped[int] = mapped_column(SmallInteger, nullable=False)

    product_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("products.id", ondelete="RESTRICT"), nullable=False
    )
    # NULL solo si products.tracks_batches = FALSE.
    batch_id: Mapped[Optional[int]] = mapped_column(
        BigInteger,
        ForeignKey("batches.id", ondelete="RESTRICT"),
        nullable=True,
    )
    location_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("inventory_locations.id", ondelete="RESTRICT"),
        nullable=False,
    )

    quantity: Mapped[Quantity] = mapped_column(Numeric(16, 4), nullable=False)
    unit_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("units_of_measure.id", ondelete="RESTRICT"),
        nullable=False,
    )
    quantity_base: Mapped[Quantity] = mapped_column(Numeric(16, 4), nullable=False)

    unit_cost: Mapped[Optional[UnitPrice]] = mapped_column(
        Numeric(16, 4), nullable=True
    )
    total_cost: Mapped[Optional[Money]] = mapped_column(Numeric(16, 2), nullable=True)
    currency: Mapped[Currency]

    # Cuando paso en la realidad, no cuando se registro.
    occurred_at: Mapped[_dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )

    # -- Referencia polimorfica: sin FK sobre reference_id (decision del ERD).
    reference_type: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    reference_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)

    # -- Autorreferencias: par del traslado y movimiento que corrige.
    # ondelete RESTRICT explicito: la tabla es append-only, ningun movimiento se
    # borra nunca. Se corrige con un movimiento inverso, no con un DELETE.
    # Nombre explicito y corto: el que arma la convencion para una tabla que se
    # referencia a si misma llega a 66 caracteres y PostgreSQL lo truncaria a 63
    # agregando un hash, dejando un nombre ilegible e imposible de recordar.
    counterpart_movement_id: Mapped[Optional[int]] = mapped_column(
        BigInteger,
        ForeignKey(
            "inventory_movements.id",
            ondelete="RESTRICT",
            name="fk_inventory_movements_counterpart",
        ),
        nullable=True,
    )
    reverses_movement_id: Mapped[Optional[int]] = mapped_column(
        BigInteger,
        ForeignKey(
            "inventory_movements.id",
            ondelete="RESTRICT",
            name="fk_inventory_movements_reverses",
        ),
        nullable=True,
    )

    reason_code: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # -- Columnas de tiempo declaradas a mano: tabla append-only sin mixin.
    created_at: Mapped[_dt.datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        default=func.now(),
    )
    created_by_id: Mapped[Optional[int]] = mapped_column(
        BigInteger,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    # -- Relaciones --------------------------------------------------------
    location: Mapped["InventoryLocation"] = relationship(
        "InventoryLocation", back_populates="movements", foreign_keys=[location_id]
    )
    product: Mapped["Product"] = relationship("Product", foreign_keys=[product_id])
    batch: Mapped[Optional["Batch"]] = relationship("Batch", foreign_keys=[batch_id])
    unit: Mapped["UnitOfMeasure"] = relationship(
        "UnitOfMeasure", foreign_keys=[unit_id]
    )
    created_by: Mapped[Optional["User"]] = relationship(
        "User", foreign_keys=[created_by_id]
    )
    # Autorreferencias many-to-one: remote_side apunta a la PK de esta tabla.
    counterpart_movement: Mapped[Optional["InventoryMovement"]] = relationship(
        "InventoryMovement",
        foreign_keys=[counterpart_movement_id],
        remote_side="InventoryMovement.id",
    )
    reverses_movement: Mapped[Optional["InventoryMovement"]] = relationship(
        "InventoryMovement",
        foreign_keys=[reverses_movement_id],
        remote_side="InventoryMovement.id",
    )

    __table_args__ = (
        enum_check("movement_type", MOVEMENT_TYPES),
        CheckConstraint("direction IN (1, -1)", name="direction_valid"),
        # Cada movement_type amarrado a su direction obligatorio.
        CheckConstraint(
            f"(movement_type IN ({_sql_list(MOVEMENT_TYPES_IN)}) AND direction = 1) "
            f"OR (movement_type IN ({_sql_list(MOVEMENT_TYPES_OUT)}) AND direction = -1)",
            name="type_direction",
        ),
        positive_check("quantity"),
        positive_check("quantity_base"),
        CheckConstraint(
            "unit_cost IS NULL OR unit_cost >= 0",
            name="unit_cost_non_negative",
        ),
        CheckConstraint(
            f"reference_type IS NULL OR reference_type IN "
            f"({_sql_list(MOVEMENT_REFERENCE_TYPES)})",
            name="reference_type_valid",
        ),
        CheckConstraint(
            "reference_type IS NULL OR reference_id IS NOT NULL",
            name="reference_id_required",
        ),
        CheckConstraint(
            f"reason_code IS NULL OR reason_code IN ({_sql_list(MOVEMENT_REASON_CODES)})",
            name="reason_code_valid",
        ),
        # El primero es el indice sobre el que se calcula cualquier saldo.
        Index(
            "ix_inventory_movements_lookup",
            "product_id",
            "batch_id",
            "location_id",
            "occurred_at",
        ),
        Index("ix_inventory_movements_occurred", text("occurred_at DESC")),
        Index("ix_inventory_movements_reference", "reference_type", "reference_id"),
        Index("ix_inventory_movements_type", "movement_type"),
    )

    # -- Utilidades de dominio --------------------------------------------
    @property
    def signed_quantity_base(self) -> Quantity:
        """Cantidad con signo, en unidad base. Base de cualquier saldo."""
        return self.quantity_base * self.direction

    @property
    def is_inbound(self) -> bool:
        return self.direction == 1

    @property
    def is_transfer(self) -> bool:
        return "TRANSFER" in self.movement_type

    @property
    def is_reversal(self) -> bool:
        return self.reverses_movement_id is not None


class InventoryBalance(Base):
    """Saldo vigente por producto, lote y ubicacion (seccion 7.5).

    Tabla **derivada** de ``inventory_movements``, mantenida por la capa de
    servicios y reconstruible con ``flask inventory rebuild-balances``. Nunca es
    la fuente de verdad. Solo lleva ``updated_at``: no es una tabla de negocio.

    El indice unico parcial ``uq_inventory_balances_no_batch`` existe porque en
    SQL NULL no es igual a NULL y sin el se crearian filas duplicadas para
    productos sin lote.
    """

    __tablename__ = "inventory_balances"

    id: Mapped[PK]

    product_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("products.id", ondelete="CASCADE"), nullable=False
    )
    batch_id: Mapped[Optional[int]] = mapped_column(
        BigInteger,
        ForeignKey("batches.id", ondelete="CASCADE"),
        nullable=True,
    )
    location_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("inventory_locations.id", ondelete="CASCADE"),
        nullable=False,
    )

    quantity_base: Mapped[Quantity] = mapped_column(
        Numeric(16, 4), nullable=False, server_default="0", default=0
    )
    # Promedio ponderado movil (seccion 9).
    average_unit_cost: Mapped[UnitPrice] = mapped_column(
        Numeric(16, 4), nullable=False, server_default="0", default=0
    )
    total_value: Mapped[Money] = mapped_column(
        Numeric(16, 2), nullable=False, server_default="0", default=0
    )

    last_movement_id: Mapped[Optional[int]] = mapped_column(
        BigInteger,
        ForeignKey("inventory_movements.id", ondelete="SET NULL"),
        nullable=True,
    )
    last_movement_at: Mapped[Optional[_dt.datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    updated_at: Mapped[_dt.datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        default=func.now(),
        onupdate=func.now(),
    )

    # -- Relaciones --------------------------------------------------------
    location: Mapped["InventoryLocation"] = relationship(
        "InventoryLocation", back_populates="balances", foreign_keys=[location_id]
    )
    product: Mapped["Product"] = relationship("Product", foreign_keys=[product_id])
    batch: Mapped[Optional["Batch"]] = relationship("Batch", foreign_keys=[batch_id])
    last_movement: Mapped[Optional["InventoryMovement"]] = relationship(
        "InventoryMovement", foreign_keys=[last_movement_id]
    )

    __table_args__ = (
        UniqueConstraint(
            "product_id",
            "batch_id",
            "location_id",
            name="uq_inventory_balances_product_id",
        ),
        # NULL <> NULL: el UNIQUE anterior no cubre el caso sin lote.
        Index(
            "uq_inventory_balances_no_batch",
            "product_id",
            "location_id",
            unique=True,
            postgresql_where=text("batch_id IS NULL"),
        ),
        CheckConstraint(
            "average_unit_cost >= 0",
            name="average_unit_cost_non_negative",
        ),
        Index("ix_inventory_balances_location_id", "location_id"),
        Index("ix_inventory_balances_batch_id", "batch_id"),
    )

    # -- Utilidades de dominio --------------------------------------------
    @property
    def is_empty(self) -> bool:
        return self.quantity_base == 0

    @property
    def is_negative(self) -> bool:
        """Saldo negativo: solo legitimo en ubicaciones con allows_negative_stock."""
        return self.quantity_base < 0


__all__ = [
    "InventoryBalance",
    "InventoryLocation",
    "InventoryMovement",
    "LOCATION_TYPES",
    "MOVEMENT_REASON_CODES",
    "MOVEMENT_REFERENCE_TYPES",
    "MOVEMENT_TYPES",
    "MOVEMENT_TYPES_IN",
    "MOVEMENT_TYPES_OUT",
]
