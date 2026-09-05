"""Modulo Terceros: parties, party_roles, addresses, party_contacts.

Seccion 3 del ERD logico v1.0.

Materializa la regla de diseno mas importante del ERD conceptual: no separar
clientes, cafeterias, proveedores e intermediarios en tablas independientes. Una
cafeteria que ademas vende cafe verde a Densa Niebla es UNA party con DOS roles.
"""

from __future__ import annotations

import datetime as _dt
from typing import TYPE_CHECKING, Any, Optional

from sqlalchemy import (
    CHAR,
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    ForeignKey,
    Index,
    Numeric,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import PK, Base, Money, enum_check, validity_check
from app.models.mixins import ActiveMixin, AuditMixin, TimestampMixin, ValidityMixin

if TYPE_CHECKING:
    from app.models.price import PriceList
    from app.models.user import User

PARTY_TYPES: tuple[str, ...] = ("NATURAL", "JURIDICA")

DOCUMENT_TYPES: tuple[str, ...] = ("CC", "NIT", "CE", "PAS", "TI", "RC", "PEP", "NIT_EXT")

TAX_REGIMES: tuple[str, ...] = (
    "SIMPLIFICADO",
    "COMUN",
    "GRAN_CONTRIBUYENTE",
    "NO_RESPONSABLE_IVA",
    "REGIMEN_SIMPLE",
)

PARTY_ROLE_CODES: tuple[str, ...] = (
    "CUSTOMER",
    "SUPPLIER",
    "COFFEE_GROWER",
    "CAFETERIA",
    "INTERMEDIARY",
    "CARRIER",
    "PROCESSOR",
    "EMPLOYEE",
)

ADDRESS_TYPES: tuple[str, ...] = ("BILLING", "SHIPPING", "BOTH", "FARM")


class Party(AuditMixin, ActiveMixin, Base):
    """Tercero del negocio: cliente, proveedor, campesino, maquilador, transportador."""

    __tablename__ = "parties"

    id: Mapped[PK]

    party_type: Mapped[str] = mapped_column(String(20), nullable=False)
    document_type: Mapped[str] = mapped_column(String(10), nullable=False)
    document_number: Mapped[str] = mapped_column(String(30), nullable=False)
    verification_digit: Mapped[Optional[int]] = mapped_column(SmallInteger, nullable=True)

    legal_name: Mapped[str] = mapped_column(String(200), nullable=False)
    trade_name: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    first_name: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    last_name: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

    email: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    phone: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    whatsapp: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)

    # -- Datos fiscales. Los valores concretos los confirma el area legal.
    tax_regime: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    tax_responsibilities: Mapped[list[Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'[]'::jsonb"), default=list
    )
    is_vat_withholding_agent: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="false", default=False
    )

    municipality_code: Mapped[Optional[str]] = mapped_column(String(5), nullable=True)
    department_code: Mapped[Optional[str]] = mapped_column(String(2), nullable=True)
    country_code: Mapped[str] = mapped_column(
        CHAR(2), nullable=False, server_default="CO", default="CO"
    )

    credit_limit: Mapped[Optional[Money]] = mapped_column(Numeric(16, 2), nullable=True)
    payment_term_days: Mapped[int] = mapped_column(
        SmallInteger, nullable=False, server_default="0", default=0
    )
    default_price_list_id: Mapped[Optional[int]] = mapped_column(
        BigInteger,
        ForeignKey("price_lists.id", ondelete="SET NULL", use_alter=True),
        nullable=True,
    )

    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # -- Relaciones --------------------------------------------------------
    party_roles: Mapped[list["PartyRole"]] = relationship(
        "PartyRole", back_populates="party", cascade="all, delete-orphan"
    )
    addresses: Mapped[list["Address"]] = relationship(
        "Address", back_populates="party", cascade="all, delete-orphan"
    )
    contacts: Mapped[list["PartyContact"]] = relationship(
        "PartyContact", back_populates="party", cascade="all, delete-orphan"
    )
    users: Mapped[list["User"]] = relationship(
        "User", back_populates="party", foreign_keys="User.party_id"
    )
    default_price_list: Mapped[Optional["PriceList"]] = relationship(
        "PriceList", foreign_keys=[default_price_list_id]
    )

    __table_args__ = (
        UniqueConstraint(
            "document_type", "document_number", name="uq_parties_document_type"
        ),
        enum_check("party_type", PARTY_TYPES),
        enum_check("document_type", DOCUMENT_TYPES),
        CheckConstraint(
            "tax_regime IS NULL OR tax_regime IN "
            "('COMUN','GRAN_CONTRIBUYENTE','NO_RESPONSABLE_IVA','REGIMEN_SIMPLE','SIMPLIFICADO')",
            name="tax_regime_valid",
        ),
        CheckConstraint(
            "document_type <> 'NIT' OR verification_digit IS NOT NULL",
            name="nit_requires_dv",
        ),
        CheckConstraint(
            "party_type <> 'NATURAL' OR (first_name IS NOT NULL AND last_name IS NOT NULL)",
            name="natural_requires_names",
        ),
        CheckConstraint(
            "credit_limit IS NULL OR credit_limit >= 0",
            name="credit_limit_non_negative",
        ),
        CheckConstraint(
            "payment_term_days >= 0", name="payment_term_non_negative"
        ),
        Index("ix_parties_legal_name", "legal_name"),
        Index("ix_parties_is_active", "is_active"),
        Index("ix_parties_document_number", "document_number"),
    )

    # -- Utilidades de dominio --------------------------------------------
    @property
    def display_name(self) -> str:
        return self.trade_name or self.legal_name

    @property
    def document_full(self) -> str:
        if self.document_type == "NIT" and self.verification_digit is not None:
            return f"{self.document_number}-{self.verification_digit}"
        return self.document_number

    def active_roles(self, on: _dt.date | None = None) -> set[str]:
        day = on or _dt.date.today()
        return {r.role_code for r in self.party_roles if r.covers(day)}

    def has_role(self, role_code: str, on: _dt.date | None = None) -> bool:
        return role_code in self.active_roles(on)

    @property
    def primary_address(self) -> Optional["Address"]:
        for addr in self.addresses:
            if addr.is_primary:
                return addr
        return None


class PartyRole(TimestampMixin, ValidityMixin, Base):
    """Rol que un tercero asume, con vigencia. Un tercero puede tener varios."""

    __tablename__ = "party_roles"

    id: Mapped[PK]
    party_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("parties.id", ondelete="CASCADE"), nullable=False
    )
    role_code: Mapped[str] = mapped_column(String(30), nullable=False)
    valid_from: Mapped[_dt.date] = mapped_column(
        Date, nullable=False, server_default=text("CURRENT_DATE")
    )
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    party: Mapped["Party"] = relationship("Party", back_populates="party_roles")

    __table_args__ = (
        UniqueConstraint(
            "party_id", "role_code", "valid_from", name="uq_party_roles_party_id"
        ),
        enum_check("role_code", PARTY_ROLE_CODES),
        validity_check(),
        Index("ix_party_roles_role_code", "role_code", "valid_to"),
    )


class Address(TimestampMixin, ActiveMixin, Base):
    """Direccion de un tercero. El tipo FARM cubre fincas sin direccion postal."""

    __tablename__ = "addresses"

    id: Mapped[PK]
    party_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("parties.id", ondelete="CASCADE"), nullable=False
    )
    label: Mapped[Optional[str]] = mapped_column(String(60), nullable=True)
    address_type: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default="BOTH", default="BOTH"
    )
    address_line: Mapped[str] = mapped_column(String(255), nullable=False)
    address_line_2: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    municipality_code: Mapped[Optional[str]] = mapped_column(String(5), nullable=True)
    municipality_name: Mapped[str] = mapped_column(String(100), nullable=False)
    department_code: Mapped[Optional[str]] = mapped_column(String(2), nullable=True)
    department_name: Mapped[str] = mapped_column(String(100), nullable=False)
    country_code: Mapped[str] = mapped_column(
        CHAR(2), nullable=False, server_default="CO", default="CO"
    )
    postal_code: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)

    # Trazabilidad de origen, no solo contacto.
    latitude: Mapped[Optional[Any]] = mapped_column(Numeric(10, 7), nullable=True)
    longitude: Mapped[Optional[Any]] = mapped_column(Numeric(10, 7), nullable=True)

    is_primary: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="false", default=False
    )

    party: Mapped["Party"] = relationship("Party", back_populates="addresses")

    __table_args__ = (
        enum_check("address_type", ADDRESS_TYPES),
        CheckConstraint(
            "latitude IS NULL OR (latitude >= -90 AND latitude <= 90)",
            name="latitude_range",
        ),
        CheckConstraint(
            "longitude IS NULL OR (longitude >= -180 AND longitude <= 180)",
            name="longitude_range",
        ),
        # Una sola direccion principal por tercero.
        Index(
            "uq_addresses_one_primary",
            "party_id",
            unique=True,
            postgresql_where=text("is_primary"),
        ),
        Index("ix_addresses_party_id", "party_id"),
    )

    @property
    def one_line(self) -> str:
        parts = [self.address_line, self.address_line_2, self.municipality_name,
                 self.department_name]
        return ", ".join(p for p in parts if p)


class PartyContact(TimestampMixin, ActiveMixin, Base):
    """Persona de contacto dentro de una organizacion (relevante en cafeterias)."""

    __tablename__ = "party_contacts"

    id: Mapped[PK]
    party_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("parties.id", ondelete="CASCADE"), nullable=False
    )
    full_name: Mapped[str] = mapped_column(String(150), nullable=False)
    position: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    email: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    phone: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    is_primary: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="false", default=False
    )

    party: Mapped["Party"] = relationship("Party", back_populates="contacts")

    __table_args__ = (
        Index(
            "uq_party_contacts_one_primary",
            "party_id",
            unique=True,
            postgresql_where=text("is_primary"),
        ),
        Index("ix_party_contacts_party_id", "party_id"),
    )


__all__ = [
    "ADDRESS_TYPES",
    "Address",
    "DOCUMENT_TYPES",
    "PARTY_ROLE_CODES",
    "PARTY_TYPES",
    "Party",
    "PartyContact",
    "PartyRole",
    "TAX_REGIMES",
]
