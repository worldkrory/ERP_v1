"""Modulo Ventas: sales, sale_items, sale_item_batches.

Seccion 10 del ERD logico v1.0 (10.1, 10.2 y 10.3).

La venta es el hecho comercial y la factura es el documento fiscal que lo
representa: por eso ``sale_number`` es un consecutivo interno distinto del
numero de factura, y la relacion con ``invoices`` no es uno a uno.
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
    desc,
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
    fraction_check,
    positive_check,
)
from app.models.mixins import AuditMixin, TimestampMixin

if TYPE_CHECKING:
    from app.models.batch import Batch
    from app.models.inventory import InventoryLocation, InventoryMovement
    from app.models.party import Address, Party
    from app.models.price import PriceList, PriceListItem
    from app.models.product import Product
    from app.models.tax import Tax
    from app.models.unit import UnitOfMeasure
    from app.models.user import User

SALE_CHANNELS: tuple[str, ...] = (
    "RETAIL",
    "CAFETERIA",
    "WHOLESALE",
    "INTERMEDIARY",
    "ONLINE",
    "EVENT",
)

SALE_STATUSES: tuple[str, ...] = (
    "DRAFT",
    "CONFIRMED",
    "DISPATCHED",
    "DELIVERED",
    "CANCELLED",
    "RETURNED",
)

SALE_PAYMENT_STATUSES: tuple[str, ...] = ("UNPAID", "PARTIAL", "PAID", "OVERDUE")

PRICE_SOURCES: tuple[str, ...] = ("PRICE_LIST", "PARTY_RULE", "MANUAL")


class Sale(AuditMixin, Base):
    """Cabecera de venta: el hecho comercial, con dos terceros posibles.

    ``party_id`` es el cliente e ``intermediary_party_id`` el intermediario que
    gestiono la venta (canal INTERMEDIARY); ambos apuntan a ``parties``.
    ``cost_total`` y ``margin_amount`` se materializan al confirmar: el margen
    de una venta de marzo debe seguir siendo el que era.

    Invariante de servicio: ``payment_status`` se mantiene desde
    ``payment_allocations``; no se calcula al vuelo porque el dashboard
    consulta cartera constantemente.
    """

    __tablename__ = "sales"

    id: Mapped[PK]

    sale_number: Mapped[str] = mapped_column(String(30), nullable=False)

    party_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("parties.id", ondelete="RESTRICT"), nullable=False
    )
    channel: Mapped[str] = mapped_column(String(25), nullable=False)
    intermediary_party_id: Mapped[Optional[int]] = mapped_column(
        BigInteger, ForeignKey("parties.id", ondelete="RESTRICT"), nullable=True
    )

    # Snapshot de la lista de precios usada al cotizar.
    price_list_id: Mapped[Optional[int]] = mapped_column(
        BigInteger,
        ForeignKey("price_lists.id", ondelete="RESTRICT"),
        nullable=True,
    )
    salesperson_user_id: Mapped[Optional[int]] = mapped_column(
        BigInteger,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    sale_date: Mapped[_dt.date] = mapped_column(Date, nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default="DRAFT", default="DRAFT"
    )
    payment_status: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default="UNPAID", default="UNPAID"
    )

    # Snapshot de las condiciones de pago del cliente.
    payment_term_days: Mapped[int] = mapped_column(
        SmallInteger, nullable=False, server_default="0", default=0
    )
    due_date: Mapped[Optional[_dt.date]] = mapped_column(Date, nullable=True)

    currency: Mapped[Currency]

    subtotal: Mapped[Money] = mapped_column(
        Numeric(16, 2), nullable=False, server_default="0", default=0
    )
    discount_total: Mapped[Money] = mapped_column(
        Numeric(16, 2), nullable=False, server_default="0", default=0
    )
    tax_total: Mapped[Money] = mapped_column(
        Numeric(16, 2), nullable=False, server_default="0", default=0
    )
    total: Mapped[Money] = mapped_column(
        Numeric(16, 2), nullable=False, server_default="0", default=0
    )
    paid_amount: Mapped[Money] = mapped_column(
        Numeric(16, 2), nullable=False, server_default="0", default=0
    )

    # Snapshots de costo y margen, materializados al confirmar la venta.
    cost_total: Mapped[Money] = mapped_column(
        Numeric(16, 2), nullable=False, server_default="0", default=0
    )
    margin_amount: Mapped[Money] = mapped_column(
        Numeric(16, 2), nullable=False, server_default="0", default=0
    )
    margin_pct: Mapped[Optional[Percent]] = mapped_column(Numeric(9, 6), nullable=True)

    freight_amount: Mapped[Money] = mapped_column(
        Numeric(16, 2), nullable=False, server_default="0", default=0
    )
    shipping_address_id: Mapped[Optional[int]] = mapped_column(
        BigInteger,
        ForeignKey("addresses.id", ondelete="SET NULL"),
        nullable=True,
    )

    confirmed_at: Mapped[Optional[_dt.datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    cancelled_at: Mapped[Optional[_dt.datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    cancellation_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    telegram_message_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    telegram_notified_at: Mapped[Optional[_dt.datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # -- Relaciones --------------------------------------------------------
    party: Mapped["Party"] = relationship("Party", foreign_keys=[party_id])
    intermediary_party: Mapped[Optional["Party"]] = relationship(
        "Party", foreign_keys=[intermediary_party_id]
    )
    price_list: Mapped[Optional["PriceList"]] = relationship(
        "PriceList", foreign_keys=[price_list_id]
    )
    salesperson: Mapped[Optional["User"]] = relationship(
        "User", foreign_keys=[salesperson_user_id]
    )
    shipping_address: Mapped[Optional["Address"]] = relationship(
        "Address", foreign_keys=[shipping_address_id]
    )
    items: Mapped[list["SaleItem"]] = relationship(
        "SaleItem", back_populates="sale", cascade="all, delete-orphan"
    )

    __table_args__ = (
        UniqueConstraint("sale_number", name="uq_sales_sale_number"),
        enum_check("channel", SALE_CHANNELS),
        enum_check("status", SALE_STATUSES),
        enum_check("payment_status", SALE_PAYMENT_STATUSES),
        CheckConstraint(
            "intermediary_party_id IS NULL OR intermediary_party_id <> party_id",
            name="intermediary_not_customer",
        ),
        CheckConstraint("total >= 0", name="total_non_negative"),
        CheckConstraint(
            "status <> 'CANCELLED' OR cancelled_at IS NOT NULL",
            name="cancelled_requires_timestamp",
        ),
        CheckConstraint(
            "payment_term_days >= 0", name="payment_term_non_negative"
        ),
        # Criticos para rendimiento (seccion 15).
        Index("ix_sales_date", desc("sale_date")),
        Index("ix_sales_party_date", "party_id", desc("sale_date")),
        Index("ix_sales_status", "status"),
        Index("ix_sales_payment_status", "payment_status", "due_date"),
        Index("ix_sales_channel", "channel", "sale_date"),
    )

    # -- Utilidades de dominio --------------------------------------------
    @property
    def balance_due(self) -> Money:
        """Saldo pendiente de cobro: total menos lo pagado."""
        return self.total - self.paid_amount

    @property
    def is_editable(self) -> bool:
        """Solo un borrador se puede editar; confirmar descuenta inventario."""
        return self.status == "DRAFT"

    @property
    def is_cancelled(self) -> bool:
        return self.status == "CANCELLED"

    @property
    def is_fully_paid(self) -> bool:
        return self.payment_status == "PAID"

    @property
    def is_overdue(self) -> bool:
        """Vencida si tiene saldo y la fecha de vencimiento ya paso."""
        if self.due_date is None or self.balance_due <= 0:
            return False
        return self.due_date < _dt.date.today()


class SaleItem(TimestampMixin, Base):
    """Linea de venta con snapshots de precio, impuesto y costo.

    Los seis campos de snapshot -- ``description``, ``unit_price``,
    ``price_list_item_id``, ``tax_rate``, ``unit_cost`` y
    ``costing_method_used`` -- congelan los valores aplicados en el momento de
    la venta. El ERD lo exige porque las ventas deben conservar el historico de
    precio y valores aplicados: si manana cambia el nombre del producto, la
    tarifa de IVA, la lista de precios o el metodo de costeo, la linea vendida
    debe seguir mostrando lo que se cobro y con que costo se calculo el margen.
    ``price_list_item_id`` conserva la trazabilidad del origen del precio y
    ``costing_method_used`` permite saber con que metodo se costeo cada linea
    aunque el sistema cambie de politica de costeo dual.

    Invariante de servicio: ``subtotal = quantity * unit_price -
    discount_amount`` y ``total = subtotal + tax_amount``.
    """

    __tablename__ = "sale_items"

    id: Mapped[PK]

    sale_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("sales.id", ondelete="CASCADE"), nullable=False
    )
    line_no: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    product_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("products.id", ondelete="RESTRICT"),
        nullable=False,
    )
    # Snapshot 1: nombre del producto al momento de la venta.
    description: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    quantity: Mapped[Quantity] = mapped_column(Numeric(16, 4), nullable=False)
    unit_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("units_of_measure.id", ondelete="RESTRICT"),
        nullable=False,
    )
    quantity_base: Mapped[Quantity] = mapped_column(Numeric(16, 4), nullable=False)

    # Snapshot 2: precio unitario efectivamente cobrado.
    unit_price: Mapped[UnitPrice] = mapped_column(Numeric(16, 4), nullable=False)
    # Snapshot 3: origen del precio en la lista vigente.
    price_list_item_id: Mapped[Optional[int]] = mapped_column(
        BigInteger,
        ForeignKey("price_list_items.id", ondelete="SET NULL"),
        nullable=True,
    )
    price_source: Mapped[str] = mapped_column(String(30), nullable=False)

    discount_pct: Mapped[Percent] = mapped_column(
        Numeric(9, 6), nullable=False, server_default="0", default=0
    )
    discount_amount: Mapped[Money] = mapped_column(
        Numeric(16, 2), nullable=False, server_default="0", default=0
    )

    tax_id: Mapped[Optional[int]] = mapped_column(
        BigInteger,
        ForeignKey("taxes.id", ondelete="RESTRICT"),
        nullable=True,
    )
    # Snapshot 4: tarifa de impuesto aplicada.
    tax_rate: Mapped[Percent] = mapped_column(
        Numeric(9, 6), nullable=False, server_default="0", default=0
    )
    tax_amount: Mapped[Money] = mapped_column(
        Numeric(16, 2), nullable=False, server_default="0", default=0
    )

    subtotal: Mapped[Money] = mapped_column(Numeric(16, 2), nullable=False)
    total: Mapped[Money] = mapped_column(Numeric(16, 2), nullable=False)

    # Snapshot 5: costo unitario aplicado segun el metodo vigente.
    unit_cost: Mapped[UnitPrice] = mapped_column(
        Numeric(16, 4), nullable=False, server_default="0", default=0
    )
    total_cost: Mapped[Money] = mapped_column(
        Numeric(16, 2), nullable=False, server_default="0", default=0
    )
    margin_amount: Mapped[Money] = mapped_column(
        Numeric(16, 2), nullable=False, server_default="0", default=0
    )
    # Snapshot 6: metodo de costeo con el que se valorizo la linea.
    costing_method_used: Mapped[Optional[str]] = mapped_column(
        String(25), nullable=True
    )

    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # -- Relaciones --------------------------------------------------------
    sale: Mapped["Sale"] = relationship("Sale", back_populates="items")
    product: Mapped["Product"] = relationship("Product", foreign_keys=[product_id])
    unit: Mapped["UnitOfMeasure"] = relationship(
        "UnitOfMeasure", foreign_keys=[unit_id]
    )
    price_list_item: Mapped[Optional["PriceListItem"]] = relationship(
        "PriceListItem", foreign_keys=[price_list_item_id]
    )
    tax: Mapped[Optional["Tax"]] = relationship("Tax", foreign_keys=[tax_id])
    batch_allocations: Mapped[list["SaleItemBatch"]] = relationship(
        "SaleItemBatch", back_populates="sale_item", cascade="all, delete-orphan"
    )

    __table_args__ = (
        UniqueConstraint("sale_id", "line_no", name="uq_sale_items_sale_id"),
        positive_check("quantity"),
        CheckConstraint("quantity_base > 0", name="quantity_base_positive"),
        CheckConstraint("unit_price >= 0", name="unit_price_non_negative"),
        enum_check("price_source", PRICE_SOURCES),
        fraction_check("discount_pct"),
        Index("ix_sale_items_sale", "sale_id"),
        Index("ix_sale_items_product", "product_id"),
    )

    # -- Utilidades de dominio --------------------------------------------
    @property
    def gross_amount(self) -> Money:
        """Importe bruto antes de descuento (cantidad por precio unitario)."""
        return self.quantity * self.unit_price

    @property
    def is_price_overridden(self) -> bool:
        """True si alguien sobreescribio el precio sugerido."""
        return self.price_source == "MANUAL"

    @property
    def allocated_quantity_base(self) -> Quantity:
        """Cantidad base ya asignada a lotes (para verificar la invariante)."""
        return sum((b.quantity_base for b in self.batch_allocations), start=0)

    @property
    def is_batch_allocation_balanced(self) -> bool:
        return self.allocated_quantity_base == self.quantity_base


class SaleItemBatch(TimestampMixin, Base):
    """Asignacion de lotes a una linea de venta: trazabilidad hacia adelante.

    Una linea puede salir de varios lotes y ubicaciones (despachar 30 libras
    con un lote abierto de 18), y sin esta tabla el costeo SPECIFIC_BATCH no es
    implementable. Guarda el costo del lote aplicado a esa porcion.

    Invariante de servicio: ``SUM(sale_item_batches.quantity_base) ==
    sale_items.quantity_base``. No se implementa como CHECK porque una
    restriccion de tabla no puede agregar filas de otra tabla; se valida en la
    capa de servicios mas una verificacion periodica de lineas descuadradas.
    """

    __tablename__ = "sale_item_batches"

    id: Mapped[PK]

    sale_item_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("sale_items.id", ondelete="CASCADE"), nullable=False
    )
    batch_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("batches.id", ondelete="RESTRICT"),
        nullable=False,
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

    unit_cost: Mapped[UnitPrice] = mapped_column(Numeric(16, 4), nullable=False)
    total_cost: Mapped[Money] = mapped_column(Numeric(16, 2), nullable=False)

    movement_id: Mapped[Optional[int]] = mapped_column(
        BigInteger,
        ForeignKey("inventory_movements.id", ondelete="SET NULL"),
        nullable=True,
    )

    # -- Relaciones --------------------------------------------------------
    sale_item: Mapped["SaleItem"] = relationship(
        "SaleItem", back_populates="batch_allocations"
    )
    batch: Mapped["Batch"] = relationship("Batch", foreign_keys=[batch_id])
    location: Mapped["InventoryLocation"] = relationship(
        "InventoryLocation", foreign_keys=[location_id]
    )
    unit: Mapped["UnitOfMeasure"] = relationship(
        "UnitOfMeasure", foreign_keys=[unit_id]
    )
    movement: Mapped[Optional["InventoryMovement"]] = relationship(
        "InventoryMovement", foreign_keys=[movement_id]
    )

    __table_args__ = (
        UniqueConstraint(
            "sale_item_id",
            "batch_id",
            "location_id",
            name="uq_sale_item_batches_sale_item_id",
        ),
        positive_check("quantity"),
        CheckConstraint(
            "quantity_base > 0", name="quantity_base_positive"
        ),
        CheckConstraint(
            "unit_cost >= 0", name="unit_cost_non_negative"
        ),
        # Critico para rendimiento (seccion 15): trazabilidad hacia adelante.
        Index("ix_sib_batch", "batch_id"),
        Index("ix_sib_sale_item", "sale_item_id"),
    )


__all__ = [
    "PRICE_SOURCES",
    "SALE_CHANNELS",
    "SALE_PAYMENT_STATUSES",
    "SALE_STATUSES",
    "Sale",
    "SaleItem",
    "SaleItemBatch",
]
