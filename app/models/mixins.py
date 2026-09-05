"""Mixins de auditoria, vigencia y estado.

Implementa la seccion 0.3 (columnas de auditoria), 0.4 (borrado logico) y
0.5 (vigencias) del ERD logico v1.0.

Regla del ERD:

* Tablas de negocio  -> AuditMixin  (created_at, updated_at, created_by_id, updated_by_id)
* Tablas de catalogo -> TimestampMixin (solo created_at, updated_at)
"""

from __future__ import annotations

import datetime as _dt
from typing import Optional

from sqlalchemy import BigInteger, Boolean, Date, DateTime, ForeignKey, func
from sqlalchemy.orm import Mapped, declared_attr, mapped_column


class TimestampMixin:
    """Marcas de tiempo. Usado por las tablas de catalogo."""

    created_at: Mapped[_dt.datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        default=func.now(),
    )
    updated_at: Mapped[_dt.datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        default=func.now(),
        onupdate=func.now(),
    )


class AuditMixin(TimestampMixin):
    """Auditoria completa. Usado por las tablas de negocio.

    Las FK a ``users`` son ON DELETE SET NULL: desactivar o eliminar un usuario
    nunca debe arrastrar documentos historicos (seccion 0.4).
    """

    @declared_attr
    def created_by_id(cls) -> Mapped[Optional[int]]:  # noqa: N805
        return mapped_column(
            BigInteger,
            ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        )

    @declared_attr
    def updated_by_id(cls) -> Mapped[Optional[int]]:  # noqa: N805
        return mapped_column(
            BigInteger,
            ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        )


class ActiveMixin:
    """Desactivacion logica para catalogos y maestros (seccion 0.4)."""

    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="true", default=True
    )


class ValidityMixin:
    """Par de vigencia para tablas de reglas (seccion 0.5).

    Una regla nunca se actualiza para cambiar su valor: se cierra con
    ``valid_to`` y se crea una nueva. El CHECK de rango y la EXCLUDE de
    solapamiento se declaran en ``__table_args__`` de cada modelo.
    """

    valid_from: Mapped[_dt.date] = mapped_column(Date, nullable=False)
    valid_to: Mapped[Optional[_dt.date]] = mapped_column(Date, nullable=True)

    @property
    def is_open_ended(self) -> bool:
        return self.valid_to is None

    def covers(self, day: _dt.date) -> bool:
        """True si la regla esta vigente en la fecha dada (rango cerrado)."""
        if day < self.valid_from:
            return False
        return self.valid_to is None or day <= self.valid_to


__all__ = ["ActiveMixin", "AuditMixin", "TimestampMixin", "ValidityMixin"]
