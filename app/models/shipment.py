"""Modulo Logistica: shipments, shipment_items, shipment_events.

Seccion 12 del ERD logico v1.0.

Recupera el modulo SHIPMENTS / LOGISTICS del ERD conceptual. Los tipos
`PROCESSOR_OUT` y `PROCESSOR_IN` conectan la logistica con la maquila: el envio
del cafe verde al trillador y su retorno son despachos reales con flete, que se
imputa via `cost_entries`. La distincion `freight_cost` / `freight_charged`
permite ver si el flete cobrado cubre el pagado.
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
    Quantity,
    enum_check,
    positive_check,
)
from app.models.mixins import AuditMixin, TimestampMixin

if TYPE_CHECKING:
    from app.models.batch import Batch
    from app.models.inventory import InventoryLocation, InventoryMovement
    from app.models.party import Address, Party
    from app.models.product import Product
    from app.models.sale import Sale, SaleItem
    from app.models.unit import UnitOfMeasure
    from app.models.user import User

SHIPMENT_TYPES: tuple[str, ...] = (
    "SALE_DELIVERY",
    "PROCESSOR_OUT",
    "PROCESSOR_IN",
    "TRANSFER",
    "RETURN",
)

SHIPMENT_STATUSES: tuple[str, ...] = (
    "PENDING",
    "DISPATCHED",
    "IN_TRANSIT",
    "DELIVERED",
    "FAILED",
    "RETURNED",
    "CANCELLED",
)

SHIPMENT_EVENT_TYPES: tuple[str, ...] = (
    "CREATED",
    "DISPATCHED",
    "IN_TRANSIT",
    "OUT_FOR_DELIVERY",
    "DELIVERED",
    "FAILED",
    "RETURNED",
    "NOTE",
)


class Shipment(AuditMixin, Base):
    """Despacho fisico de mercancia: entrega de venta, maquila, traslado o devolucion.

    Invariante de servicio: el estado debe avanzar de forma coherente con
    `dispatched_at` y `delivered_at`; el descargue de inventario se registra en
    `inventory_movements` desde cada `shipment_items.movement_id`.
    """

    __tablename__ = "shipments"

    id: Mapped[PK]

    shipment_number: Mapped[str] = mapped_column(String(30), nullable=False)

    sale_id: Mapped[Optional[int]] = mapped_column(
        BigInteger,
        ForeignKey("sales.id", ondelete="RESTRICT"),
        nullable=True,
    )
    # Transportador registrado como tercero con rol CARRIER.
    carrier_party_id: Mapped[Optional[int]] = mapped_column(
        BigInteger, ForeignKey("parties.id", ondelete="RESTRICT"), nullable=True
    )
    # Nombre libre para transportadores ocasionales sin registro.
    carrier_name: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)

    shipment_type: Mapped[str] = mapped_column(String(25), nullable=False)

    origin_location_id: Mapped[Optional[int]] = mapped_column(
        BigInteger,
        ForeignKey("inventory_locations.id", ondelete="RESTRICT"),
        nullable=True,
    )
    destination_location_id: Mapped[Optional[int]] = mapped_column(
        BigInteger,
        ForeignKey("inventory_locations.id", ondelete="RESTRICT"),
        nullable=True,
    )
    destination_address_id: Mapped[Optional[int]] = mapped_column(
        BigInteger,
        ForeignKey("addresses.id", ondelete="SET NULL"),
        nullable=True,
    )

    tracking_number: Mapped[Optional[str]] = mapped_column(String(80), nullable=True)
    tracking_url: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    status: Mapped[str] = mapped_column(
        String(25), nullable=False, server_default="PENDING", default="PENDING"
    )
    dispatched_at: Mapped[Optional[_dt.datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    estimated_delivery_date: Mapped[Optional[_dt.date]] = mapped_column(Date, nullable=True)
    delivered_at: Mapped[Optional[_dt.datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    received_by: Mapped[Optional[str]] = mapped_column(String(150), nullable=True)

    total_weight_kg: Mapped[Optional[Quantity]] = mapped_column(Numeric(16, 4), nullable=True)
    package_count: Mapped[Optional[int]] = mapped_column(SmallInteger, nullable=True)

    # Lo que Densa Niebla paga vs. lo que cobra al cliente.
    freight_cost: Mapped[Money] = mapped_column(
        Numeric(16, 2), nullable=False, server_default="0", default=0
    )
    freight_charged: Mapped[Money] = mapped_column(
        Numeric(16, 2), nullable=False, server_default="0", default=0
    )
    insurance_cost: Mapped[Money] = mapped_column(
        Numeric(16, 2), nullable=False, server_default="0", default=0
    )
    currency: Mapped[Currency]

    carrier_document_number: Mapped[Optional[str]] = mapped_column(String(60), nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # -- Relaciones --------------------------------------------------------
    items: Mapped[list["ShipmentItem"]] = relationship(
        "ShipmentItem", back_populates="shipment", cascade="all, delete-orphan"
    )
    events: Mapped[list["ShipmentEvent"]] = relationship(
        "ShipmentEvent",
        back_populates="shipment",
        cascade="all, delete-orphan",
        order_by="ShipmentEvent.occurred_at",
    )
    sale: Mapped[Optional["Sale"]] = relationship("Sale", foreign_keys=[sale_id])
    carrier_party: Mapped[Optional["Party"]] = relationship(
        "Party", foreign_keys=[carrier_party_id]
    )
    origin_location: Mapped[Optional["InventoryLocation"]] = relationship(
        "InventoryLocation", foreign_keys=[origin_location_id]
    )
    destination_location: Mapped[Optional["InventoryLocation"]] = relationship(
        "InventoryLocation", foreign_keys=[destination_location_id]
    )
    destination_address: Mapped[Optional["Address"]] = relationship(
        "Address", foreign_keys=[destination_address_id]
    )

    __table_args__ = (
        UniqueConstraint("shipment_number", name="uq_shipments_shipment_number"),
        enum_check("shipment_type", SHIPMENT_TYPES),
        enum_check("status", SHIPMENT_STATUSES),
        CheckConstraint(
            "origin_location_id IS NULL OR destination_location_id IS NULL "
            "OR origin_location_id <> destination_location_id",
            name="origin_differs_destination",
        ),
        CheckConstraint("freight_cost >= 0", name="freight_cost_non_negative"),
        CheckConstraint(
            "freight_charged >= 0", name="freight_charged_non_negative"
        ),
        CheckConstraint(
            "insurance_cost >= 0", name="insurance_cost_non_negative"
        ),
        Index("ix_shipments_sale", "sale_id"),
        Index("ix_shipments_status", "status"),
        Index("ix_shipments_carrier", "carrier_party_id"),
        Index("ix_shipments_tracking", "tracking_number"),
    )

    # -- Utilidades de dominio --------------------------------------------
    @property
    def carrier_display(self) -> Optional[str]:
        """Nombre del transportador: el tercero registrado o el ocasional."""
        if self.carrier_party is not None:
            return self.carrier_party.display_name
        return self.carrier_name

    @property
    def is_closed(self) -> bool:
        return self.status in ("DELIVERED", "RETURNED", "CANCELLED")

    @property
    def is_in_transit(self) -> bool:
        return self.status in ("DISPATCHED", "IN_TRANSIT")

    @property
    def freight_margin(self) -> Money:
        """Diferencia entre el flete cobrado y el pagado (fuga de margen si es < 0)."""
        return self.freight_charged - self.freight_cost


class ShipmentItem(TimestampMixin, Base):
    """Linea de despacho. Permite despachos parciales y registra los lotes enviados."""

    __tablename__ = "shipment_items"

    id: Mapped[PK]

    shipment_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("shipments.id", ondelete="CASCADE"), nullable=False
    )
    sale_item_id: Mapped[Optional[int]] = mapped_column(
        BigInteger,
        ForeignKey("sale_items.id", ondelete="RESTRICT"),
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

    movement_id: Mapped[Optional[int]] = mapped_column(
        BigInteger,
        ForeignKey("inventory_movements.id", ondelete="SET NULL"),
        nullable=True,
    )

    # -- Relaciones --------------------------------------------------------
    shipment: Mapped["Shipment"] = relationship("Shipment", back_populates="items")
    sale_item: Mapped[Optional["SaleItem"]] = relationship(
        "SaleItem", foreign_keys=[sale_item_id]
    )
    product: Mapped["Product"] = relationship("Product", foreign_keys=[product_id])
    batch: Mapped[Optional["Batch"]] = relationship("Batch", foreign_keys=[batch_id])
    unit: Mapped["UnitOfMeasure"] = relationship("UnitOfMeasure", foreign_keys=[unit_id])
    movement: Mapped[Optional["InventoryMovement"]] = relationship(
        "InventoryMovement", foreign_keys=[movement_id]
    )

    __table_args__ = (
        positive_check("quantity"),
        positive_check("quantity_base"),
        Index("ix_shipment_items_shipment_id", "shipment_id"),
    )


class ShipmentEvent(Base):
    """Rastreo append-only del despacho (seccion 12.3).

    Sin `updated_at` ni `updated_by_id`: un evento de rastreo no se corrige, se
    agrega otro.
    """

    __tablename__ = "shipment_events"

    id: Mapped[PK]

    shipment_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("shipments.id", ondelete="CASCADE"), nullable=False
    )
    event_type: Mapped[str] = mapped_column(String(30), nullable=False)
    location_text: Mapped[Optional[str]] = mapped_column(String(150), nullable=True)
    message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    occurred_at: Mapped[_dt.datetime] = mapped_column(
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
    shipment: Mapped["Shipment"] = relationship("Shipment", back_populates="events")
    created_by: Mapped[Optional["User"]] = relationship(
        "User", foreign_keys=[created_by_id]
    )

    __table_args__ = (
        enum_check("event_type", SHIPMENT_EVENT_TYPES),
        Index("ix_shipment_events_shipment", "shipment_id", "occurred_at"),
    )


__all__ = [
    "SHIPMENT_EVENT_TYPES",
    "SHIPMENT_STATUSES",
    "SHIPMENT_TYPES",
    "Shipment",
    "ShipmentEvent",
    "ShipmentItem",
]
