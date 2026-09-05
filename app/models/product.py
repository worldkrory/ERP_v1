"""Modulo Productos: product_categories, products, coffee_profiles.

Seccion 4.3, 4.5 y 4.6 del ERD logico v1.0.

``products`` es el maestro unico: cafe verde, pergamino, tostado, molido, insumos
y servicios de maquila viven en la misma tabla, diferenciados por
``product_kind``. Los atributos que solo aplican al cafe se separan en
``coffee_profiles`` para no llenar de columnas nulables el maestro.
"""

from __future__ import annotations

import decimal
from typing import TYPE_CHECKING, Optional

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import PK, Base, Quantity, enum_check
from app.models.mixins import ActiveMixin, AuditMixin, TimestampMixin
from app.models.tax import Tax  # noqa: F401  (registra el mapper de taxes)
from app.models.unit import UnitOfMeasure  # noqa: F401  (registra units_of_measure)

if TYPE_CHECKING:
    from app.models.unit import UnitConversion

PRODUCT_KINDS: tuple[str, ...] = (
    "FINISHED",
    "RAW_MATERIAL",
    "SEMI_FINISHED",
    "SUPPLY",
    "SERVICE",
)

COSTING_METHODS: tuple[str, ...] = (
    "SPECIFIC_BATCH",
    "WEIGHTED_AVERAGE",
    "SYSTEM_DEFAULT",
)

PROCESS_METHODS: tuple[str, ...] = ("LAVADO", "HONEY", "NATURAL", "ANAEROBICO", "OTRO")

ROAST_LEVELS: tuple[str, ...] = ("CLARO", "MEDIO", "MEDIO_OSCURO", "OSCURO")

GRIND_TYPES: tuple[str, ...] = ("GRANO", "GRUESO", "MEDIO", "FINO", "EXPRESO")


class ProductCategory(TimestampMixin, ActiveMixin, Base):
    """Categoria de producto con autorreferencia de uno o dos niveles.

    Seccion 4.3 del ERD. No se usa ``ltree``: la complejidad no se justifica.

    Invariante de servicio: la profundidad maxima de dos niveles se valida en
    la capa de servicios, no con constraint.
    """

    __tablename__ = "product_categories"

    id: Mapped[PK]

    code: Mapped[str] = mapped_column(String(30), nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    parent_id: Mapped[Optional[int]] = mapped_column(
        BigInteger,
        ForeignKey("product_categories.id", ondelete="RESTRICT"),
        nullable=True,
    )

    # -- Relaciones --------------------------------------------------------
    parent: Mapped[Optional["ProductCategory"]] = relationship(
        "ProductCategory", back_populates="children", remote_side=lambda: [ProductCategory.id]
    )
    children: Mapped[list["ProductCategory"]] = relationship(
        "ProductCategory", back_populates="parent"
    )
    products: Mapped[list["Product"]] = relationship(
        "Product", back_populates="category", foreign_keys="Product.category_id"
    )

    __table_args__ = (
        UniqueConstraint("code", name="uq_product_categories_code"),
        CheckConstraint("parent_id IS NULL OR parent_id <> id", name="no_self_parent"),
        Index("ix_product_categories_parent_id", "parent_id"),
    )

    # -- Utilidades de dominio --------------------------------------------
    @property
    def is_root(self) -> bool:
        return self.parent_id is None

    @property
    def full_path(self) -> str:
        return f"{self.parent.name} / {self.name}" if self.parent else self.name


class Product(AuditMixin, ActiveMixin, Base):
    """Maestro de productos y servicios (seccion 4.5 del ERD).

    ``costing_method`` implementa el costeo dual: ``SYSTEM_DEFAULT`` delega en
    la configuracion global (``app_settings``) y solo los cafes de origen unico
    se marcan como ``SPECIFIC_BATCH``.

    Invariante de servicio: la coherencia de dimension entre ``base_unit_id``,
    ``sales_unit_id`` y ``purchase_unit_id`` (o la existencia de una conversion
    especifica de producto) se valida en la capa de servicios.
    """

    __tablename__ = "products"

    id: Mapped[PK]

    sku: Mapped[str] = mapped_column(String(40), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    product_kind: Mapped[str] = mapped_column(String(25), nullable=False)

    category_id: Mapped[Optional[int]] = mapped_column(
        BigInteger,
        ForeignKey("product_categories.id", ondelete="SET NULL"),
        nullable=True,
    )
    base_unit_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("units_of_measure.id", ondelete="RESTRICT"),
        nullable=False,
    )
    sales_unit_id: Mapped[Optional[int]] = mapped_column(
        BigInteger,
        ForeignKey("units_of_measure.id", ondelete="RESTRICT"),
        nullable=True,
    )
    purchase_unit_id: Mapped[Optional[int]] = mapped_column(
        BigInteger,
        ForeignKey("units_of_measure.id", ondelete="RESTRICT"),
        nullable=True,
    )
    tax_id: Mapped[Optional[int]] = mapped_column(
        BigInteger, ForeignKey("taxes.id", ondelete="RESTRICT"), nullable=True
    )

    # FALSE para insumos como etiquetas o bolsas y para servicios.
    tracks_batches: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="true", default=True
    )
    costing_method: Mapped[str] = mapped_column(
        String(25),
        nullable=False,
        server_default="SYSTEM_DEFAULT",
        default="SYSTEM_DEFAULT",
    )

    is_sellable: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="true", default=True
    )
    is_purchasable: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="false", default=False
    )
    is_produced: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="false", default=False
    )

    # Alerta de reposicion, expresada en unidad base.
    min_stock: Mapped[Optional[Quantity]] = mapped_column(Numeric(16, 4), nullable=True)
    # Peso unitario para calculo de flete.
    weight_kg: Mapped[Optional[Quantity]] = mapped_column(Numeric(16, 4), nullable=True)
    barcode: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    image_path: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    # -- Relaciones --------------------------------------------------------
    category: Mapped[Optional["ProductCategory"]] = relationship(
        "ProductCategory", back_populates="products", foreign_keys=[category_id]
    )
    base_unit: Mapped["UnitOfMeasure"] = relationship(
        "UnitOfMeasure", back_populates="products_base", foreign_keys=[base_unit_id]
    )
    sales_unit: Mapped[Optional["UnitOfMeasure"]] = relationship(
        "UnitOfMeasure", back_populates="products_sales", foreign_keys=[sales_unit_id]
    )
    purchase_unit: Mapped[Optional["UnitOfMeasure"]] = relationship(
        "UnitOfMeasure",
        back_populates="products_purchase",
        foreign_keys=[purchase_unit_id],
    )
    tax: Mapped[Optional["Tax"]] = relationship(
        "Tax", back_populates="products", foreign_keys=[tax_id]
    )
    coffee_profile: Mapped[Optional["CoffeeProfile"]] = relationship(
        "CoffeeProfile",
        back_populates="product",
        uselist=False,
        cascade="all, delete-orphan",
    )
    unit_conversions: Mapped[list["UnitConversion"]] = relationship(
        "UnitConversion",
        back_populates="product",
        foreign_keys="UnitConversion.product_id",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        UniqueConstraint("sku", name="uq_products_sku"),
        enum_check("product_kind", PRODUCT_KINDS),
        enum_check("costing_method", COSTING_METHODS),
        CheckConstraint(
            "tracks_batches = FALSE OR product_kind <> 'SERVICE'",
            name="service_without_batches",
        ),
        CheckConstraint(
            "is_sellable OR is_purchasable OR is_produced",
            name="at_least_one_usage",
        ),
        CheckConstraint(
            "min_stock IS NULL OR min_stock >= 0", name="min_stock_non_negative"
        ),
        CheckConstraint(
            "weight_kg IS NULL OR weight_kg >= 0", name="weight_non_negative"
        ),
        # UNIQUE de barcode solo cuando no es NULL (seccion 15).
        Index(
            "uq_products_barcode",
            "barcode",
            unique=True,
            postgresql_where=text("barcode IS NOT NULL"),
        ),
        Index("ix_products_product_kind", "product_kind"),
        Index("ix_products_is_active", "is_active"),
        Index("ix_products_sku", "sku"),
    )

    # -- Utilidades de dominio --------------------------------------------
    @property
    def display_name(self) -> str:
        return f"[{self.sku}] {self.name}"

    @property
    def is_service(self) -> bool:
        return self.product_kind == "SERVICE"

    @property
    def is_coffee(self) -> bool:
        """True si el producto tiene perfil de cafe asociado."""
        return self.coffee_profile is not None

    @property
    def uses_system_costing(self) -> bool:
        """True cuando el costeo se delega a la configuracion global."""
        return self.costing_method == "SYSTEM_DEFAULT"

    @property
    def effective_sales_unit_id(self) -> int:
        """Unidad de venta por defecto; cae a la unidad base si no hay una."""
        return self.sales_unit_id or self.base_unit_id

    @property
    def effective_purchase_unit_id(self) -> int:
        """Unidad de compra por defecto; cae a la unidad base si no hay una."""
        return self.purchase_unit_id or self.base_unit_id


class CoffeeProfile(TimestampMixin, Base):
    """Atributos exclusivos del cafe, en relacion 1:1 opcional con products.

    Seccion 4.6 del ERD. El UNIQUE sobre ``product_id`` es lo que hace la
    relacion 1:1 real y no 1:N por accidente.
    """

    __tablename__ = "coffee_profiles"

    id: Mapped[PK]

    product_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("products.id", ondelete="CASCADE"), nullable=False
    )
    variety: Mapped[Optional[str]] = mapped_column(String(80), nullable=True)
    process_method: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    roast_level: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    grind_type: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    altitude_min_masl: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    altitude_max_masl: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    # Escala SCA de 0 a 100.
    cupping_score: Mapped[Optional[decimal.Decimal]] = mapped_column(
        Numeric(5, 2), nullable=True
    )
    sensory_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    # Gramaje del empaque.
    packaging_grams: Mapped[Optional[decimal.Decimal]] = mapped_column(
        Numeric(10, 2), nullable=True
    )

    # -- Relaciones --------------------------------------------------------
    product: Mapped["Product"] = relationship(
        "Product", back_populates="coffee_profile", foreign_keys=[product_id]
    )

    __table_args__ = (
        UniqueConstraint("product_id", name="uq_coffee_profiles_product_id"),
        CheckConstraint(
            "process_method IS NULL OR process_method IN "
            "('ANAEROBICO','HONEY','LAVADO','NATURAL','OTRO')",
            name="process_method_valid",
        ),
        CheckConstraint(
            "roast_level IS NULL OR roast_level IN "
            "('CLARO','MEDIO','MEDIO_OSCURO','OSCURO')",
            name="roast_level_valid",
        ),
        CheckConstraint(
            "grind_type IS NULL OR grind_type IN "
            "('EXPRESO','FINO','GRANO','GRUESO','MEDIO')",
            name="grind_type_valid",
        ),
        CheckConstraint(
            "cupping_score IS NULL OR (cupping_score >= 0 AND cupping_score <= 100)",
            name="cupping_score_range",
        ),
        CheckConstraint(
            "altitude_min_masl IS NULL OR altitude_max_masl IS NULL "
            "OR altitude_max_masl >= altitude_min_masl",
            name="altitude_range",
        ),
        CheckConstraint(
            "packaging_grams IS NULL OR packaging_grams > 0",
            name="packaging_positive",
        ),
    )

    # -- Utilidades de dominio --------------------------------------------
    @property
    def altitude_label(self) -> Optional[str]:
        if self.altitude_min_masl is None and self.altitude_max_masl is None:
            return None
        if self.altitude_min_masl is not None and self.altitude_max_masl is not None:
            return f"{self.altitude_min_masl}-{self.altitude_max_masl} msnm"
        value = self.altitude_min_masl or self.altitude_max_masl
        return f"{value} msnm"

    @property
    def is_specialty(self) -> bool:
        """Cafe especial segun la SCA: puntaje de taza de 80 o mas."""
        return self.cupping_score is not None and self.cupping_score >= 80


__all__ = [
    "COSTING_METHODS",
    "CoffeeProfile",
    "GRIND_TYPES",
    "PROCESS_METHODS",
    "PRODUCT_KINDS",
    "Product",
    "ProductCategory",
    "ROAST_LEVELS",
]
