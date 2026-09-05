"""Modulo Facturacion DIAN: fiscal_resolutions, invoices, invoice_items, invoice_events.

Seccion 11 del ERD logico v1.0.

La estructura de datos queda completa para firma, transmision, validacion y
respuestas de la DIAN; lo juridico lo maneja el area legal. El modulo esta
desacoplado de ventas: una factura puede respaldar una venta (`sale_id`), una
compra a campesino no obligado a facturar (`purchase_id`, documento soporte) u
otra factura (`related_invoice_id`, notas credito y debito).
"""

from __future__ import annotations

import datetime as _dt
from typing import TYPE_CHECKING, Any, Optional

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
    Time,
    UniqueConstraint,
    desc,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import (
    PK,
    Base,
    Currency,
    Day,
    Money,
    Percent,
    Quantity,
    UnitPrice,
    enum_check,
    positive_check,
    validity_check,
)
from app.models.mixins import ActiveMixin, AuditMixin, TimestampMixin

if TYPE_CHECKING:
    from app.models.party import Party
    from app.models.product import Product
    from app.models.purchase import Purchase, PurchaseItem
    from app.models.sale import Sale, SaleItem
    from app.models.unit import UnitOfMeasure
    from app.models.user import User

# Tipos de documento que la DIAN autoriza por resolucion (incluye NOMINA).
FISCAL_DOCUMENT_TYPES: tuple[str, ...] = (
    "FACTURA_VENTA",
    "NOTA_CREDITO",
    "NOTA_DEBITO",
    "DOCUMENTO_SOPORTE",
    "NOMINA",
)

# Tipos de documento que este modulo emite (nomina no se factura aqui).
INVOICE_DOCUMENT_TYPES: tuple[str, ...] = (
    "FACTURA_VENTA",
    "NOTA_CREDITO",
    "NOTA_DEBITO",
    "DOCUMENTO_SOPORTE",
)

DIAN_ENVIRONMENTS: tuple[str, ...] = ("HABILITACION", "PRODUCCION")

DIAN_STATUSES: tuple[str, ...] = (
    "DRAFT",
    "GENERATED",
    "SIGNED",
    "SENT",
    "ACCEPTED",
    "REJECTED",
    "CANCELLED",
)

PAYMENT_FORMS: tuple[str, ...] = ("CONTADO", "CREDITO")

INVOICE_EVENT_TYPES: tuple[str, ...] = (
    "GENERATED",
    "SIGNED",
    "SENT",
    "ACCEPTED",
    "REJECTED",
    "EMAILED",
    "CANCELLED",
    "RETRY",
    "ERROR",
)


class FiscalResolution(AuditMixin, ActiveMixin, Base):
    """Resolucion de numeracion DIAN: rango autorizado, clave tecnica y vigencia.

    Invariante de servicio: `current_number` se incrementa con
    ``SELECT ... FOR UPDATE`` sobre la fila para que el consecutivo fiscal no
    tenga huecos ni duplicados (seccion 11.1).
    """

    __tablename__ = "fiscal_resolutions"

    id: Mapped[PK]

    resolution_number: Mapped[str] = mapped_column(String(40), nullable=False)
    document_type: Mapped[str] = mapped_column(String(30), nullable=False)
    prefix: Mapped[str] = mapped_column(String(10), nullable=False)

    range_from: Mapped[int] = mapped_column(BigInteger, nullable=False)
    range_to: Mapped[int] = mapped_column(BigInteger, nullable=False)
    current_number: Mapped[int] = mapped_column(BigInteger, nullable=False)

    technical_key: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    # Las resoluciones si tienen vencimiento: valid_to es NOT NULL aqui.
    valid_from: Mapped[Day] = mapped_column(Date, nullable=False)
    valid_to: Mapped[Day] = mapped_column(Date, nullable=False)

    # Separado porque la habilitacion ante la DIAN exige documentos de prueba
    # cuyos consecutivos no pueden mezclarse con los reales.
    environment: Mapped[str] = mapped_column(
        String(15), nullable=False, server_default="HABILITACION", default="HABILITACION"
    )

    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # -- Relaciones --------------------------------------------------------
    invoices: Mapped[list["Invoice"]] = relationship(
        "Invoice", back_populates="resolution"
    )

    __table_args__ = (
        UniqueConstraint(
            "prefix",
            "document_type",
            "resolution_number",
            name="uq_fiscal_resolutions_prefix",
        ),
        enum_check("document_type", FISCAL_DOCUMENT_TYPES),
        enum_check("environment", DIAN_ENVIRONMENTS),
        CheckConstraint("range_to > range_from", name="range_order"),
        CheckConstraint(
            "current_number >= range_from - 1 AND current_number <= range_to",
            name="current_number_in_range",
        ),
        validity_check(),
    )

    # -- Utilidades de dominio --------------------------------------------
    @property
    def remaining_numbers(self) -> int:
        """Consecutivos autorizados que quedan sin usar."""
        return int(self.range_to) - int(self.current_number)

    @property
    def is_exhausted(self) -> bool:
        return self.remaining_numbers <= 0

    def is_valid_on(self, day: _dt.date) -> bool:
        return self.valid_from <= day <= self.valid_to


class Invoice(AuditMixin, Base):
    """Documento electronico emitido: factura de venta, nota o documento soporte.

    Los totales se materializan y no se recalculan: una factura emitida es
    inmutable (seccion 11.2).

    Invariante de servicio: la suma de `invoice_items.total` debe cuadrar con
    `total`; el consecutivo debe caer dentro del rango de `resolution_id`.
    """

    __tablename__ = "invoices"

    id: Mapped[PK]

    document_type: Mapped[str] = mapped_column(String(30), nullable=False)
    resolution_id: Mapped[Optional[int]] = mapped_column(
        BigInteger,
        ForeignKey("fiscal_resolutions.id", ondelete="RESTRICT"),
        nullable=True,
    )
    prefix: Mapped[str] = mapped_column(String(10), nullable=False)
    consecutive: Mapped[int] = mapped_column(BigInteger, nullable=False)
    full_number: Mapped[str] = mapped_column(String(30), nullable=False)

    sale_id: Mapped[Optional[int]] = mapped_column(
        BigInteger,
        ForeignKey("sales.id", ondelete="RESTRICT"),
        nullable=True,
    )
    purchase_id: Mapped[Optional[int]] = mapped_column(
        BigInteger,
        ForeignKey("purchases.id", ondelete="RESTRICT"),
        nullable=True,
    )
    party_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("parties.id", ondelete="RESTRICT"), nullable=False
    )
    # Autorreferencia: la factura que la nota credito o debito afecta.
    related_invoice_id: Mapped[Optional[int]] = mapped_column(
        BigInteger,
        ForeignKey("invoices.id", ondelete="RESTRICT"),
        nullable=True,
    )

    issue_date: Mapped[Day] = mapped_column(Date, nullable=False)
    # La DIAN exige hora de emision con zona horaria.
    issue_time: Mapped[Optional[_dt.time]] = mapped_column(Time(timezone=True), nullable=True)
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
    withholding_total: Mapped[Money] = mapped_column(
        Numeric(16, 2), nullable=False, server_default="0", default=0
    )
    total: Mapped[Money] = mapped_column(
        Numeric(16, 2), nullable=False, server_default="0", default=0
    )

    payment_means: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    payment_form: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)

    # -- Firma y transmision ----------------------------------------------
    cufe: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    uuid: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    qr_data: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    xml_signed: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    xml_path: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    pdf_path: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    dian_status: Mapped[str] = mapped_column(
        String(25), nullable=False, server_default="DRAFT", default="DRAFT"
    )
    dian_track_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    dian_response: Mapped[Optional[dict[str, Any]]] = mapped_column(JSONB, nullable=True)
    dian_errors: Mapped[Optional[dict[str, Any]]] = mapped_column(JSONB, nullable=True)

    sent_at: Mapped[Optional[_dt.datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    accepted_at: Mapped[Optional[_dt.datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    email_sent_at: Mapped[Optional[_dt.datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # -- Relaciones --------------------------------------------------------
    resolution: Mapped[Optional["FiscalResolution"]] = relationship(
        "FiscalResolution", back_populates="invoices"
    )
    items: Mapped[list["InvoiceItem"]] = relationship(
        "InvoiceItem",
        back_populates="invoice",
        cascade="all, delete-orphan",
        order_by="InvoiceItem.line_no",
    )
    events: Mapped[list["InvoiceEvent"]] = relationship(
        "InvoiceEvent",
        back_populates="invoice",
        cascade="all, delete-orphan",
        order_by="InvoiceEvent.occurred_at",
    )
    party: Mapped["Party"] = relationship("Party", foreign_keys=[party_id])
    sale: Mapped[Optional["Sale"]] = relationship("Sale", foreign_keys=[sale_id])
    purchase: Mapped[Optional["Purchase"]] = relationship(
        "Purchase", foreign_keys=[purchase_id]
    )
    related_invoice: Mapped[Optional["Invoice"]] = relationship(
        "Invoice",
        remote_side="Invoice.id",
        foreign_keys=[related_invoice_id],
        back_populates="referencing_invoices",
    )
    referencing_invoices: Mapped[list["Invoice"]] = relationship(
        "Invoice",
        foreign_keys=[related_invoice_id],
        back_populates="related_invoice",
    )

    __table_args__ = (
        UniqueConstraint(
            "prefix", "consecutive", "document_type", name="uq_invoices_prefix"
        ),
        UniqueConstraint("full_number", name="uq_invoices_full_number"),
        enum_check("document_type", INVOICE_DOCUMENT_TYPES),
        enum_check("dian_status", DIAN_STATUSES),
        CheckConstraint(
            "payment_form IS NULL OR payment_form IN ('CONTADO','CREDITO')",
            name="payment_form_valid",
        ),
        CheckConstraint(
            "document_type NOT IN ('NOTA_CREDITO','NOTA_DEBITO') "
            "OR related_invoice_id IS NOT NULL",
            name="note_requires_related",
        ),
        CheckConstraint(
            "document_type <> 'DOCUMENTO_SOPORTE' OR purchase_id IS NOT NULL",
            name="support_requires_purchase",
        ),
        CheckConstraint(
            "document_type = 'DOCUMENTO_SOPORTE' OR sale_id IS NOT NULL",
            name="requires_sale",
        ),
        # Indice unico parcial: el CUFE solo existe una vez firmado.
        Index("uq_invoices_cufe", "cufe", unique=True, postgresql_where=text("cufe IS NOT NULL")),
        Index("ix_invoices_party", "party_id", desc("issue_date")),
        Index("ix_invoices_dian_status", "dian_status"),
        Index("ix_invoices_sale", "sale_id"),
        Index("ix_invoices_issue_date", desc("issue_date")),
    )

    # -- Utilidades de dominio --------------------------------------------
    @property
    def is_credit_note(self) -> bool:
        return self.document_type == "NOTA_CREDITO"

    @property
    def is_debit_note(self) -> bool:
        return self.document_type == "NOTA_DEBITO"

    @property
    def is_support_document(self) -> bool:
        return self.document_type == "DOCUMENTO_SOPORTE"

    @property
    def is_accepted(self) -> bool:
        return self.dian_status == "ACCEPTED"

    @property
    def is_pending_dian(self) -> bool:
        """True si el documento aun no tiene respuesta definitiva de la DIAN."""
        return self.dian_status in ("DRAFT", "GENERATED", "SIGNED", "SENT")

    @property
    def is_signed(self) -> bool:
        return self.cufe is not None


class InvoiceItem(TimestampMixin, Base):
    """Linea de factura. Todos los campos son snapshot: la factura es autocontenida.

    `product_id` es nulable y `description` no lo es a proposito: la factura
    debe reimprimirse identica en cinco anos aunque el producto se renombre o
    se descontinue (seccion 11.3).
    """

    __tablename__ = "invoice_items"

    id: Mapped[PK]

    invoice_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("invoices.id", ondelete="CASCADE"), nullable=False
    )
    line_no: Mapped[int] = mapped_column(SmallInteger, nullable=False)

    sale_item_id: Mapped[Optional[int]] = mapped_column(
        BigInteger,
        ForeignKey("sale_items.id", ondelete="SET NULL"),
        nullable=True,
    )
    purchase_item_id: Mapped[Optional[int]] = mapped_column(
        BigInteger,
        ForeignKey("purchase_items.id", ondelete="SET NULL"),
        nullable=True,
    )
    product_id: Mapped[Optional[int]] = mapped_column(
        BigInteger,
        ForeignKey("products.id", ondelete="RESTRICT"),
        nullable=True,
    )

    description: Mapped[str] = mapped_column(String(255), nullable=False)
    product_code: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)

    quantity: Mapped[Quantity] = mapped_column(Numeric(16, 4), nullable=False)
    unit_id: Mapped[Optional[int]] = mapped_column(
        BigInteger,
        ForeignKey("units_of_measure.id", ondelete="RESTRICT"),
        nullable=True,
    )
    unit_dian_code: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    unit_price: Mapped[UnitPrice] = mapped_column(Numeric(16, 4), nullable=False)

    discount_amount: Mapped[Money] = mapped_column(
        Numeric(16, 2), nullable=False, server_default="0", default=0
    )
    tax_code: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    tax_rate: Mapped[Percent] = mapped_column(
        Numeric(9, 6), nullable=False, server_default="0", default=0
    )
    tax_amount: Mapped[Money] = mapped_column(
        Numeric(16, 2), nullable=False, server_default="0", default=0
    )
    subtotal: Mapped[Money] = mapped_column(Numeric(16, 2), nullable=False)
    total: Mapped[Money] = mapped_column(Numeric(16, 2), nullable=False)

    # -- Relaciones --------------------------------------------------------
    invoice: Mapped["Invoice"] = relationship("Invoice", back_populates="items")
    sale_item: Mapped[Optional["SaleItem"]] = relationship(
        "SaleItem", foreign_keys=[sale_item_id]
    )
    purchase_item: Mapped[Optional["PurchaseItem"]] = relationship(
        "PurchaseItem", foreign_keys=[purchase_item_id]
    )
    product: Mapped[Optional["Product"]] = relationship(
        "Product", foreign_keys=[product_id]
    )
    unit: Mapped[Optional["UnitOfMeasure"]] = relationship(
        "UnitOfMeasure", foreign_keys=[unit_id]
    )

    __table_args__ = (
        UniqueConstraint("invoice_id", "line_no", name="uq_invoice_items_invoice_id"),
        positive_check("quantity"),
        CheckConstraint(
            "discount_amount >= 0", name="discount_non_negative"
        ),
        Index("ix_invoice_items_invoice_id", "invoice_id"),
    )


class InvoiceEvent(Base):
    """Bitacora append-only de la interaccion con la DIAN (seccion 11.4).

    Sin `updated_at` ni `updated_by_id`: un evento nunca se modifica. Es la
    unica evidencia utilizable cuando hay que explicar un rechazo.
    """

    __tablename__ = "invoice_events"

    id: Mapped[PK]

    invoice_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("invoices.id", ondelete="CASCADE"), nullable=False
    )
    event_type: Mapped[str] = mapped_column(String(30), nullable=False)
    status_before: Mapped[Optional[str]] = mapped_column(String(25), nullable=True)
    status_after: Mapped[Optional[str]] = mapped_column(String(25), nullable=True)
    payload: Mapped[Optional[dict[str, Any]]] = mapped_column(JSONB, nullable=True)
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
    invoice: Mapped["Invoice"] = relationship("Invoice", back_populates="events")
    created_by: Mapped[Optional["User"]] = relationship(
        "User", foreign_keys=[created_by_id]
    )

    __table_args__ = (
        enum_check("event_type", INVOICE_EVENT_TYPES),
        Index("ix_invoice_events_invoice", "invoice_id", "occurred_at"),
    )


__all__ = [
    "DIAN_ENVIRONMENTS",
    "DIAN_STATUSES",
    "FISCAL_DOCUMENT_TYPES",
    "FiscalResolution",
    "INVOICE_DOCUMENT_TYPES",
    "INVOICE_EVENT_TYPES",
    "Invoice",
    "InvoiceEvent",
    "InvoiceItem",
    "PAYMENT_FORMS",
]
