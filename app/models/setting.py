"""Modulo Configuracion: app_settings, document_sequences.

Seccion 14 del ERD logico v1.0.

`app_settings` es el catalogo clave-valor de politicas globales (metodo de
costeo, base de reparto de fletes, datos de la empresa para el XML DIAN).
`document_sequences` genera los consecutivos internos, que no se derivan del
`id` de la tabla porque un `id` puede tener huecos por transacciones abortadas.
Los consecutivos fiscales no viven aqui: viven en `fiscal_resolutions`.
"""

from __future__ import annotations

import datetime as _dt
import decimal
import json
from typing import Any, Optional

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    Index,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import PK, Base, enum_check
from app.models.mixins import AuditMixin

SETTING_VALUE_TYPES: tuple[str, ...] = (
    "STRING",
    "INTEGER",
    "DECIMAL",
    "BOOLEAN",
    "DATE",
    "JSON",
)

DOCUMENT_SEQUENCE_CODES: tuple[str, ...] = (
    "SALE",
    "PURCHASE",
    "PRODUCTION_ORDER",
    "SHIPMENT",
    "PAYMENT",
    "EXPENSE",
)

# Claves iniciales necesarias (seccion 14.1). Referencia para el comando de
# siembra: clave -> (value_type, proposito). No se usa en el mapeo ORM.
INITIAL_APP_SETTINGS: dict[str, tuple[str, str]] = {
    "default_costing_method": ("STRING", "WEIGHTED_AVERAGE o SPECIFIC_BATCH"),
    "costing_method_changed_at": (
        "DATE",
        "Fecha del ultimo cambio de politica, para explicar quiebres en la serie",
    ),
    "allow_negative_stock": (
        "BOOLEAN",
        "Politica global, sobreescribible por ubicacion",
    ),
    "freight_allocation_basis": ("STRING", "VALUE o WEIGHT"),
    "byproduct_cost_allocation": ("STRING", "NONE, MARKET_VALUE o MANUAL"),
    "default_currency": ("STRING", "COP"),
    "rounding_mode": ("STRING", "HALF_UP"),
    "company_nit": ("STRING", "Para el XML de facturacion"),
    "company_legal_name": ("STRING", "Razon social de la empresa"),
    "dian_environment": ("STRING", "HABILITACION o PRODUCCION"),
    "waste_tolerance_pct": ("DECIMAL", "Umbral para alertar mermas anomalas"),
}


class AppSetting(AuditMixin, Base):
    """Parametro global del sistema, guardado como texto con su tipo declarado.

    Invariante de servicio: cambiar `default_costing_method` obliga a registrar
    `costing_method_changed_at`; las claves con `is_editable = FALSE` solo se
    modifican por migracion o siembra.
    """

    __tablename__ = "app_settings"

    id: Mapped[PK]

    key: Mapped[str] = mapped_column(String(60), nullable=False)
    value: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    value_type: Mapped[str] = mapped_column(String(20), nullable=False)
    group_name: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    is_editable: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="true", default=True
    )
    changed_at: Mapped[Optional[_dt.datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    __table_args__ = (
        UniqueConstraint("key", name="uq_app_settings_key"),
        enum_check("value_type", SETTING_VALUE_TYPES),
        Index("ix_app_settings_group_name", "group_name"),
    )

    # -- Serializacion -----------------------------------------------------
    # Esta conversion vive en el modelo porque es serializacion del propio
    # registro, no logica de negocio.
    @property
    def typed_value(self) -> Any:
        """Devuelve `value` convertido segun `value_type`. NULL sigue siendo None."""
        raw = self.value
        if raw is None:
            return None
        kind = (self.value_type or "STRING").upper()
        if kind == "STRING":
            return raw
        if kind == "INTEGER":
            return int(raw)
        if kind == "DECIMAL":
            return decimal.Decimal(raw)
        if kind == "BOOLEAN":
            return raw.strip().lower() in ("true", "t", "1", "yes", "y", "si")
        if kind == "DATE":
            return _dt.date.fromisoformat(raw.strip())
        if kind == "JSON":
            return json.loads(raw)
        raise ValueError(f"value_type no soportado: {self.value_type!r}")

    @property
    def is_json(self) -> bool:
        return self.value_type == "JSON"


class DocumentSequence(AuditMixin, Base):
    """Consecutivo interno por tipo de documento (seccion 14.2).

    Invariante de servicio: la obtencion del siguiente numero usa
    ``SELECT ... FOR UPDATE`` sobre la fila y, si `resets_yearly`, reinicia
    `next_number` cuando `current_year` cambia. Ese incremento vive en
    `services/numbering.py`: aqui solo se formatea, sin mutar nada.
    """

    __tablename__ = "document_sequences"

    id: Mapped[PK]

    code: Mapped[str] = mapped_column(String(30), nullable=False)
    prefix: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    # Ej. '{prefix}-{year}-{number:04d}'
    pattern: Mapped[str] = mapped_column(String(40), nullable=False)
    next_number: Mapped[int] = mapped_column(
        BigInteger, nullable=False, server_default="1", default=1
    )
    resets_yearly: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="true", default=True
    )
    current_year: Mapped[Optional[int]] = mapped_column(SmallInteger, nullable=True)

    __table_args__ = (
        UniqueConstraint("code", name="uq_document_sequences_code"),
        enum_check("code", DOCUMENT_SEQUENCE_CODES),
        CheckConstraint("next_number >= 1", name="next_number_min"),
        CheckConstraint(
            "current_year IS NULL OR current_year >= 2000",
            name="current_year_range",
        ),
    )

    # -- Utilidades de dominio --------------------------------------------
    def format_number(self, number: int, year: int | None = None) -> str:
        """Aplica `pattern` a un numero dado. No incrementa ni persiste nada."""
        resolved_year = year or self.current_year or _dt.date.today().year
        return self.pattern.format(
            prefix=self.prefix or "",
            code=self.code,
            year=resolved_year,
            short_year=int(resolved_year) % 100,
            number=int(number),
        )

    @property
    def preview_next(self) -> str:
        """Como se veria el siguiente numero, sin consumirlo."""
        return self.format_number(self.next_number)


__all__ = [
    "AppSetting",
    "DOCUMENT_SEQUENCE_CODES",
    "DocumentSequence",
    "INITIAL_APP_SETTINGS",
    "SETTING_VALUE_TYPES",
]
