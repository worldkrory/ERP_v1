"""Modulo Compras: purchases, purchase_items.

Seccion 6 del ERD logico v1.0.

Registra el abastecimiento: compra de cafe verde a campesinos, compra a
proveedores, servicios y activos. Es el origen documental del costo de entrada
del inventario: ``purchase_items.landed_unit_cost`` es el dato que alimenta el
costeo de cada lote.
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
from app.models.mixins import AuditMixin, TimestampMixin

if TYPE_CHECKING:
    from app.models.batch import Batch
    from app.models.inventory import InventoryLocation
    from app.models.party import Party
    from app.models.product import Product
    from app.models.tax import Tax
    from app.models.uom import UnitOfMeasure

PURCHASE_TYPES: tuple[str, ...] = ("COFFEE_GROWER", "SUPPLIER", "SERVICE", "ASSET")

PURCHASE_STATUSES: tuple[str, ...] = ("DRAFT", "CONFIRMED", "RECEIVED", "CANCELLED")

PURCHASE_PAYMENT_STATUSES: tuple[str, ...] = ("UNPAID", "PARTIAL", "PAID")

SUPPLIER_DOCUMENT_TYPES: tuple[str, ...] = (
    "FACTURA",
    "DOCUMENTO_SOPORTE",
    "RECIBO",
    "NINGUNO",
)


class Purchase(AuditMixin, Base):
    """Cabecera de compra a un proveedor o a un campesino (seccion 6.1).

    ``supplier_document_type = 'DOCUMENTO_SOPORTE'`` cubre la compra a un
    campesino no obligado a facturar: el documento electronico lo emite Densa
    Niebla desde el modulo de facturacion (seccion 11).

    Invariante de servicio: ``total`` = subtotal - discount_total + tax_total
    + freight_amount - withholding_total, y la distribucion de
    ``freight_amount`` entre las lineas segun ``app_settings``.
    """

    __tablename__ = "purchases"

    id: Mapped[PK]

    purchase_number: Mapped[str] = mapped_column(String(30), nullable=False)
    party_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("parties.id", ondelete="RESTRICT"), nullable=False
    )
    purchase_type: Mapped[str] = mapped_column(String(25), nullable=False)
    purchase_date: Mapped[_dt.date] = mapped_column(Date, nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default="DRAFT", default="DRAFT"
    )
    destination_location_id: Mapped[Optional[int]] = mapped_column(
        BigInteger,
        ForeignKey("inventory_locations.id", ondelete="RESTRICT"),
        nullable=True,
    )

    currency: Mapped[Currency]

    # -- Totales. Se recalculan en la capa de servicios a partir de las lineas.
    subtotal: Mapped[Money] = mapped_column(
        Numeric(16, 2), nullable=False, server_default="0", default=0
    )
    discount_total: Mapped[Money] = mapped_column(
        Numeric(16, 2), nullable=False, server_default="0", default=0
    )
    tax_total: Mapped[Money] = mapped_column(
        Numeric(16, 2), nullable=False, server_default="0", default=0
    )
    # Retencion en la fuente practicada al productor.
    withholding_total: Mapped[Money] = mapped_column(
        Numeric(16, 2), nullable=False, server_default="0", default=0
    )
    freight_amount: Mapped[Money] = mapped_column(
        Numeric(16, 2), nullable=False, server_default="0", default=0
    )
    total: Mapped[Money] = mapped_column(
        Numeric(16, 2), nullable=False, server_default="0", default=0
    )

    payment_status: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default="UNPAID", default="UNPAID"
    )

    supplier_document_type: Mapped[Optional[str]] = mapped_column(
        String(30), nullable=True
    )
    supplier_document_number: Mapped[Optional[str]] = mapped_column(
        String(40), nullable=True
    )

    received_at: Mapped[Optional[_dt.datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # -- Relaciones --------------------------------------------------------
    items: Mapped[list["PurchaseItem"]] = relationship(
        "PurchaseItem",
        back_populates="purchase",
        cascade="all, delete-orphan",
        order_by="PurchaseItem.line_no",
    )
    party: Mapped["Party"] = relationship("Party", foreign_keys=[party_id])
    destination_location: Mapped[Optional["InventoryLocation"]] = relationship(
        "InventoryLocation", foreign_keys=[destination_location_id]
    )

    __table_args__ = (
        UniqueConstraint("purchase_number", name="uq_purchases_purchase_number"),
        enum_check("purchase_type", PURCHASE_TYPES),
        enum_check("status", PURCHASE_STATUSES),
        enum_check("payment_status", PURCHASE_PAYMENT_STATUSES),
        CheckConstraint(
            "supplier_document_type IS NULL OR supplier_document_type IN "
            "('DOCUMENTO_SOPORTE','FACTURA','NINGUNO','RECIBO')",
            name="supplier_document_type_valid",
        ),
        CheckConstraint("subtotal >= 0", name="subtotal_non_negative"),
        CheckConstraint(
            "discount_total >= 0", name="discount_total_non_negative"
        ),
        CheckConstraint("tax_total >= 0", name="tax_total_non_negative"),
        CheckConstraint(
            "withholding_total >= 0",
            name="withholding_total_non_negative",
        ),
        CheckConstraint(
            "freight_amount >= 0", name="freight_amount_non_negative"
        ),
        CheckConstraint("total >= 0", name="total_non_negative"),
        Index("ix_purchases_party_date", "party_id", "purchase_date"),
        Index("ix_purchases_status", "status"),
    )

    # -- Utilidades de dominio --------------------------------------------
    @property
    def is_open(self) -> bool:
        """True si la compra aun admite cambios en sus lineas."""
        return self.status in ("DRAFT", "CONFIRMED")

    @property
    def is_received(self) -> bool:
        return self.status == "RECEIVED"

    @property
    def net_payable(self) -> Money:
        """Valor a pagar al proveedor: total menos retenciones."""
        return self.total - self.withholding_total


class PurchaseItem(TimestampMixin, Base):
    """Linea de compra (seccion 6.2). Al recibirse origina un lote.

    Invariante de servicio: ``landed_unit_cost`` =
    (subtotal - discount_amount + allocated_freight) / quantity_base. Los
    impuestos descontables y las retenciones no entran al costo.
    """

    __tablename__ = "purchase_items"

    id: Mapped[PK]

    purchase_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("purchases.id", ondelete="CASCADE"), nullable=False
    )
    line_no: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    product_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("products.id", ondelete="RESTRICT"), nullable=False
    )
    # Dependencia circular con batches: batches.purchase_item_id apunta de
    # vuelta a esta tabla, por eso use_alter=True en ambas FK.
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

    unit_price: Mapped[UnitPrice] = mapped_column(Numeric(16, 4), nullable=False)
    discount_amount: Mapped[Money] = mapped_column(
        Numeric(16, 2), nullable=False, server_default="0", default=0
    )

    tax_id: Mapped[Optional[int]] = mapped_column(
        BigInteger, ForeignKey("taxes.id", ondelete="RESTRICT"), nullable=True
    )
    # Snapshot de la tarifa vigente al momento de la compra.
    tax_rate: Mapped[Percent] = mapped_column(
        Numeric(9, 6), nullable=False, server_default="0", default=0
    )
    tax_amount: Mapped[Money] = mapped_column(
        Numeric(16, 2), nullable=False, server_default="0", default=0
    )
    # Flete de cabecera distribuido a esta linea.
    allocated_freight: Mapped[Money] = mapped_column(
        Numeric(16, 2), nullable=False, server_default="0", default=0
    )

    subtotal: Mapped[Money] = mapped_column(Numeric(16, 2), nullable=False)
    total: Mapped[Money] = mapped_column(Numeric(16, 2), nullable=False)
    # Costo puesto en bodega, en unidad base. Alimenta el inventario.
    landed_unit_cost: Mapped[UnitPrice] = mapped_column(Numeric(16, 4), nullable=False)

    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # -- Relaciones --------------------------------------------------------
    purchase: Mapped["Purchase"] = relationship(
        "Purchase", back_populates="items", foreign_keys=[purchase_id]
    )
    # Lote creado al recibir esta linea. foreign_keys explicito en ambos lados
    # para que SQLAlchemy no confunda esta FK con batches.purchase_item_id.
    batch: Mapped[Optional["Batch"]] = relationship(
        "Batch",
        back_populates="source_purchase_items",
        foreign_keys=[batch_id],
    )
    origin_batches: Mapped[list["Batch"]] = relationship(
        "Batch",
        back_populates="purchase_item",
        foreign_keys="Batch.purchase_item_id",
    )
    product: Mapped["Product"] = relationship("Product", foreign_keys=[product_id])
    unit: Mapped["UnitOfMeasure"] = relationship(
        "UnitOfMeasure", foreign_keys=[unit_id]
    )
    tax: Mapped[Optional["Tax"]] = relationship("Tax", foreign_keys=[tax_id])

    __table_args__ = (
        UniqueConstraint("purchase_id", "line_no", name="uq_purchase_items_purchase_id"),
        positive_check("quantity"),
        positive_check("quantity_base"),
        CheckConstraint("unit_price >= 0", name="unit_price_non_negative"),
        CheckConstraint(
            "discount_amount >= 0",
            name="discount_amount_non_negative",
        ),
        CheckConstraint("tax_rate >= 0", name="tax_rate_non_negative"),
        CheckConstraint(
            "allocated_freight >= 0",
            name="allocated_freight_non_negative",
        ),
        CheckConstraint(
            "landed_unit_cost >= 0",
            name="landed_unit_cost_non_negative",
        ),
        Index("ix_purchase_items_purchase_id", "purchase_id"),
        Index("ix_purchase_items_product_id", "product_id"),
        Index("ix_purchase_items_batch_id", "batch_id"),
    )

    # -- Utilidades de dominio --------------------------------------------
    @property
    def landed_total(self) -> Money:
        """Base de costeo de la linea, sin impuestos ni retenciones."""
        return self.subtotal - self.discount_amount + self.allocated_freight


__all__ = [
    "PURCHASE_PAYMENT_STATUSES",
    "PURCHASE_STATUSES",
    "PURCHASE_TYPES",
    "Purchase",
    "PurchaseItem",
    "SUPPLIER_DOCUMENT_TYPES",
]
