"""Modulo Precios: price_lists, price_list_items, party_price_rules.

Seccion 5 (5.1 a 5.3) del ERD logico v1.0.

El ERD conceptual exige que la tarifa general y la condicion particular esten
desacopladas: `price_list_items` guarda la tarifa del canal y
`party_price_rules` la excepcion negociada con un tercero.

El algoritmo de resolucion de precio de la seccion 5.3 del ERD (FIXED_PRICE de
la party -> lista por LIST_ASSIGNMENT -> parties.default_price_list_id -> lista
is_default del canal -> ERROR si no hay precio, y luego los descuentos por
priority) NO se implementa aqui: vive en ``app/services/pricing.py``. El
resultado se materializa como snapshot en ``sale_items``.
"""

from __future__ import annotations

import datetime as _dt
from typing import TYPE_CHECKING, Optional

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
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
    UnitPrice,
    daterange_expr,
    enum_check,
    validity_check,
)
from app.models.mixins import ActiveMixin, AuditMixin, ValidityMixin

if TYPE_CHECKING:
    from app.models.party import Party
    from app.models.product import Product, ProductCategory
    from app.models.uom import UnitOfMeasure

PRICE_LIST_CHANNELS: tuple[str, ...] = (
    "RETAIL",
    "CAFETERIA",
    "WHOLESALE",
    "INTERMEDIARY",
    "EXPORT",
    "INTERNAL",
)

PARTY_PRICE_RULE_TYPES: tuple[str, ...] = (
    "LIST_ASSIGNMENT",
    "DISCOUNT_PCT",
    "DISCOUNT_AMOUNT",
    "FIXED_PRICE",
)


class PriceList(AuditMixin, ActiveMixin, ValidityMixin, Base):
    """Tarifa vigente de un canal comercial (seccion 5.1 del ERD).

    ``includes_tax`` define si el precio almacenado ya trae IVA: al consumidor
    final se cotiza con IVA incluido y a la cafeteria sin IVA.

    Invariante de servicio: solo una lista por canal puede ser is_default y
    activa a la vez (garantizada por el indice unico parcial).
    """

    __tablename__ = "price_lists"

    id: Mapped[PK]

    code: Mapped[str] = mapped_column(String(30), nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    channel: Mapped[str] = mapped_column(String(25), nullable=False)
    currency: Mapped[Currency]

    includes_tax: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="false", default=False
    )
    is_default: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="false", default=False
    )

    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # -- Relaciones --------------------------------------------------------
    # Party.default_price_list apunta a esta tabla sin back_populates (ver
    # party.py), por eso aqui no se declara el lado inverso.
    items: Mapped[list["PriceListItem"]] = relationship(
        "PriceListItem", back_populates="price_list", cascade="all, delete-orphan"
    )
    party_rules: Mapped[list["PartyPriceRule"]] = relationship(
        "PartyPriceRule", back_populates="price_list"
    )

    __table_args__ = (
        UniqueConstraint("code", name="uq_price_lists_code"),
        enum_check("channel", PRICE_LIST_CHANNELS),
        validity_check(),
        # Una sola lista por defecto y activa por canal.
        Index(
            "uq_price_lists_one_default",
            "channel",
            unique=True,
            postgresql_where=text("is_default AND is_active"),
        ),
    )

    @property
    def is_current(self) -> bool:
        """True si la lista esta activa y vigente hoy."""
        return self.is_active and self.covers(_dt.date.today())


class PriceListItem(AuditMixin, ActiveMixin, ValidityMixin, Base):
    """Precio unitario de un producto en una lista, por unidad y por volumen.

    Seccion 5.2 del ERD. El precio va atado a ``unit_id``: la misma libra
    suelta y la caja de 12 no valen lo mismo por unidad.
    """

    __tablename__ = "price_list_items"

    id: Mapped[PK]

    price_list_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("price_lists.id", ondelete="CASCADE"), nullable=False
    )
    product_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("products.id", ondelete="RESTRICT"),
        nullable=False,
    )
    unit_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("units_of_measure.id", ondelete="RESTRICT"),
        nullable=False,
    )

    unit_price: Mapped[UnitPrice] = mapped_column(Numeric(16, 4), nullable=False)
    min_quantity: Mapped[UnitPrice] = mapped_column(
        Numeric(16, 4), nullable=False, server_default="0", default=0
    )
    max_quantity: Mapped[Optional[UnitPrice]] = mapped_column(
        Numeric(16, 4), nullable=True
    )

    # -- Relaciones --------------------------------------------------------
    price_list: Mapped["PriceList"] = relationship("PriceList", back_populates="items")
    product: Mapped["Product"] = relationship("Product", foreign_keys=[product_id])
    unit: Mapped["UnitOfMeasure"] = relationship(
        "UnitOfMeasure", foreign_keys=[unit_id]
    )

    __table_args__ = (
        CheckConstraint(
            "unit_price >= 0", name="unit_price_non_negative"
        ),
        CheckConstraint(
            "min_quantity >= 0", name="min_quantity_non_negative"
        ),
        CheckConstraint(
            "max_quantity IS NULL OR max_quantity >= min_quantity",
            name="quantity_range",
        ),
        validity_check(),
        # Sin solapamiento de cantidad ni de vigencia para la misma
        # combinacion lista/producto/unidad.
        ExcludeConstraint(
            ("price_list_id", "="),
            ("product_id", "="),
            ("unit_id", "="),
            (
                text(
                    "numrange(min_quantity, COALESCE(max_quantity, 'infinity'::numeric), '[]')"
                ),
                "&&",
            ),
            (text(daterange_expr()), "&&"),
            using="gist",
            name="price_list_items_no_overlap",
        ),
        # Indice critico de la seccion 15: resolucion de precio por linea.
        Index(
            "ix_price_list_items_lookup",
            "price_list_id",
            "product_id",
            "valid_from",
            "valid_to",
        ),
    )

    def covers_quantity(self, quantity: UnitPrice) -> bool:
        """True si la cantidad cae dentro del tramo de volumen (rango cerrado)."""
        if quantity < self.min_quantity:
            return False
        return self.max_quantity is None or quantity <= self.max_quantity


class PartyPriceRule(AuditMixin, ActiveMixin, ValidityMixin, Base):
    """Condicion particular de precio negociada con un tercero.

    Seccion 5.3 del ERD. Segun ``rule_type`` asigna una lista, aplica un
    descuento porcentual o de monto, o fija un precio.

    Invariante de servicio: el orden de precedencia y la aplicacion de
    descuentos por ``priority`` los resuelve ``app/services/pricing.py``.
    """

    __tablename__ = "party_price_rules"

    id: Mapped[PK]

    party_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("parties.id", ondelete="CASCADE"), nullable=False
    )
    rule_type: Mapped[str] = mapped_column(String(25), nullable=False)

    price_list_id: Mapped[Optional[int]] = mapped_column(
        BigInteger, ForeignKey("price_lists.id", ondelete="RESTRICT"), nullable=True
    )
    product_id: Mapped[Optional[int]] = mapped_column(
        BigInteger,
        ForeignKey("products.id", ondelete="CASCADE"),
        nullable=True,
    )
    category_id: Mapped[Optional[int]] = mapped_column(
        BigInteger,
        ForeignKey("product_categories.id", ondelete="RESTRICT"),
        nullable=True,
    )
    unit_id: Mapped[Optional[int]] = mapped_column(
        BigInteger,
        ForeignKey("units_of_measure.id", ondelete="RESTRICT"),
        nullable=True,
    )

    value: Mapped[Optional[UnitPrice]] = mapped_column(Numeric(16, 4), nullable=True)
    min_quantity: Mapped[UnitPrice] = mapped_column(
        Numeric(16, 4), nullable=False, server_default="0", default=0
    )
    priority: Mapped[int] = mapped_column(
        SmallInteger, nullable=False, server_default="100", default=100
    )

    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # -- Relaciones --------------------------------------------------------
    party: Mapped["Party"] = relationship("Party", foreign_keys=[party_id])
    price_list: Mapped[Optional["PriceList"]] = relationship(
        "PriceList", back_populates="party_rules", foreign_keys=[price_list_id]
    )
    product: Mapped[Optional["Product"]] = relationship(
        "Product", foreign_keys=[product_id]
    )
    category: Mapped[Optional["ProductCategory"]] = relationship(
        "ProductCategory", foreign_keys=[category_id]
    )
    unit: Mapped[Optional["UnitOfMeasure"]] = relationship(
        "UnitOfMeasure", foreign_keys=[unit_id]
    )

    __table_args__ = (
        enum_check("rule_type", PARTY_PRICE_RULE_TYPES),
        CheckConstraint(
            "rule_type <> 'LIST_ASSIGNMENT' OR price_list_id IS NOT NULL",
            name="list_assignment_requires_list",
        ),
        CheckConstraint(
            "rule_type <> 'FIXED_PRICE' OR (value IS NOT NULL AND unit_id IS NOT NULL)",
            name="fixed_price_requires_value_unit",
        ),
        CheckConstraint(
            "rule_type NOT IN ('DISCOUNT_PCT','DISCOUNT_AMOUNT') OR value IS NOT NULL",
            name="discount_requires_value",
        ),
        CheckConstraint(
            "product_id IS NULL OR category_id IS NULL",
            name="product_xor_category",
        ),
        CheckConstraint(
            "rule_type <> 'DISCOUNT_PCT' OR (value >= 0 AND value <= 1)",
            name="discount_pct_fraction",
        ),
        CheckConstraint(
            "min_quantity >= 0", name="min_quantity_non_negative"
        ),
        validity_check(),
        Index("ix_party_price_rules_party_id", "party_id", "rule_type", "priority"),
    )

    @property
    def scope_label(self) -> str:
        """Etiqueta legible del alcance de la regla."""
        if self.product_id is not None:
            return "PRODUCT"
        if self.category_id is not None:
            return "CATEGORY"
        return "ALL"


__all__ = [
    "PARTY_PRICE_RULE_TYPES",
    "PRICE_LIST_CHANNELS",
    "PartyPriceRule",
    "PriceList",
    "PriceListItem",
]
