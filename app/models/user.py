"""Modulo Seguridad: users, roles, user_roles.

Seccion 2 del ERD logico v1.0.

Un ``User`` es quien opera el ERP. Una ``Party`` es un tercero del negocio. Son
tablas distintas a proposito; se vinculan por ``users.party_id`` cuando la misma
persona es ambas cosas.
"""

from __future__ import annotations

import datetime as _dt
from typing import TYPE_CHECKING, Any, Optional

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import PK, Base
from app.models.mixins import TimestampMixin

if TYPE_CHECKING:
    from app.models.party import Party

ROLE_CODES: tuple[str, ...] = (
    "ADMIN",
    "VENTAS",
    "PRODUCCION",
    "INVENTARIO",
    "CONTABILIDAD",
    "CONSULTA",
)


class User(TimestampMixin, Base):
    """Usuario interno del sistema."""

    __tablename__ = "users"

    id: Mapped[PK]
    email: Mapped[str] = mapped_column(String(255), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    full_name: Mapped[str] = mapped_column(String(150), nullable=False)

    # use_alter: parties tambien referencia users por auditoria. Alembic debe
    # crear esta FK despues de ambas tablas.
    party_id: Mapped[Optional[int]] = mapped_column(
        BigInteger,
        ForeignKey("parties.id", ondelete="SET NULL", use_alter=True),
        nullable=True,
    )

    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="true", default=True
    )
    is_superuser: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="false", default=False
    )

    last_login_at: Mapped[Optional[_dt.datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    failed_login_count: Mapped[int] = mapped_column(
        SmallInteger, nullable=False, server_default="0", default=0
    )
    locked_until: Mapped[Optional[_dt.datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    password_changed_at: Mapped[Optional[_dt.datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    party: Mapped[Optional["Party"]] = relationship(
        "Party", foreign_keys=[party_id], back_populates="users"
    )
    user_roles: Mapped[list["UserRole"]] = relationship(
        "UserRole",
        back_populates="user",
        foreign_keys="UserRole.user_id",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        UniqueConstraint("email", name="uq_users_email"),
        Index("ix_users_is_active", "is_active"),
    )

    # -- Flask-Login -------------------------------------------------------
    @property
    def is_authenticated(self) -> bool:
        return True

    @property
    def is_anonymous(self) -> bool:
        return False

    def get_id(self) -> str:
        return str(self.id)

    @property
    def is_locked(self) -> bool:
        if self.locked_until is None:
            return False
        return self.locked_until > _dt.datetime.now(_dt.timezone.utc)

    @property
    def role_codes(self) -> set[str]:
        return {ur.role.code for ur in self.user_roles if ur.role is not None}

    def has_role(self, code: str) -> bool:
        return self.is_superuser or code in self.role_codes

    def has_permission(self, permission: str) -> bool:
        if self.is_superuser:
            return True
        for ur in self.user_roles:
            if ur.role is not None and permission in (ur.role.permissions or []):
                return True
        return False


class Role(TimestampMixin, Base):
    """Rol funcional. Los permisos viven en JSONB por decision de la seccion 2.2."""

    __tablename__ = "roles"

    id: Mapped[PK]
    code: Mapped[str] = mapped_column(String(40), nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    permissions: Mapped[list[Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'[]'::jsonb"), default=list
    )
    is_system: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="false", default=False
    )

    user_roles: Mapped[list["UserRole"]] = relationship(
        "UserRole", back_populates="role"
    )

    __table_args__ = (UniqueConstraint("code", name="uq_roles_code"),)


class UserRole(Base):
    """Asignacion de rol. Tabla puente sin auditoria completa."""

    __tablename__ = "user_roles"

    id: Mapped[PK]
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    role_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("roles.id", ondelete="RESTRICT"), nullable=False
    )
    assigned_at: Mapped[_dt.datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        default=func.now(),
    )
    assigned_by_id: Mapped[Optional[int]] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    user: Mapped["User"] = relationship(
        "User", foreign_keys=[user_id], back_populates="user_roles"
    )
    role: Mapped["Role"] = relationship("Role", back_populates="user_roles")
    assigned_by: Mapped[Optional["User"]] = relationship(
        "User", foreign_keys=[assigned_by_id]
    )

    __table_args__ = (
        UniqueConstraint("user_id", "role_id", name="uq_user_roles_user_id"),
    )


__all__ = ["ROLE_CODES", "Role", "User", "UserRole"]
