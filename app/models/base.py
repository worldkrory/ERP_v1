"""Base declarativa y tipos canonicos del ERP Densa Niebla.

Implementa la seccion 0 del ERD logico v1.0:

* 0.2 Tipos de dato  -> alias anotados (Money, Quantity, Factor, Percent, ...)
* 0.7 Convencion de nombres de restricciones -> NAMING_CONVENTION

Este modulo NO depende de Flask, a proposito: permite validar los modelos y
generar DDL sin levantar la aplicacion. Flask-SQLAlchemy se engancha en
``app/extensions.py`` con:

    from app.models.base import Base
    db = SQLAlchemy(model_class=Base)
"""

from __future__ import annotations

import datetime as _dt
import decimal
from typing import Annotated, Any

from sqlalchemy import (
    CHAR,
    BigInteger,
    CheckConstraint,
    Date,
    DateTime,
    MetaData,
    Numeric,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, mapped_column, registry

# ---------------------------------------------------------------------------
# 0.7 Convencion de nombres de restricciones
# ---------------------------------------------------------------------------
# Debe existir ANTES de generar la migracion inicial. Anadirlo despues no
# renombra lo ya creado en la base de datos.
NAMING_CONVENTION: dict[str, str] = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    # La plantilla antepone "ck_<tabla>_". Por eso los CHECK de los modelos se
    # declaran con el nombre CORTO de la regla ("precio_no_negativo"), nunca con
    # el prefijo repetido: eso generaba nombres de hasta 79 caracteres que
    # PostgreSQL truncaba en 63, dejandolos imposibles de referenciar despues.
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}

metadata_obj = MetaData(naming_convention=NAMING_CONVENTION)


# ---------------------------------------------------------------------------
# 0.2 Tipos de dato canonicos
# ---------------------------------------------------------------------------
# Se declaran como alias anotados para que ningun modelo pueda equivocarse en
# la precision. Nunca usar float para dinero ni para cantidades.

# Clave primaria: BIGINT identity. Nunca INTEGER.
PK = Annotated[int, mapped_column(BigInteger, primary_key=True, autoincrement=True)]

# Clave foranea BIGINT (el ForeignKey se declara en cada modelo).
FK = Annotated[int, mapped_column(BigInteger)]

# Dinero: NUMERIC(16,2).
Money = Annotated[decimal.Decimal, mapped_column(Numeric(16, 2))]

# Cantidades y precios unitarios: NUMERIC(16,4).
Quantity = Annotated[decimal.Decimal, mapped_column(Numeric(16, 4))]
UnitPrice = Annotated[decimal.Decimal, mapped_column(Numeric(16, 4))]

# Factores de conversion: NUMERIC(20,10). Se multiplican en cadena.
Factor = Annotated[decimal.Decimal, mapped_column(Numeric(20, 10))]

# Porcentajes almacenados como fraccion (0.19 = 19%): NUMERIC(9,6).
Percent = Annotated[decimal.Decimal, mapped_column(Numeric(9, 6))]

# Fecha y hora: TIMESTAMPTZ obligatorio (America/Bogota).
TS = Annotated[_dt.datetime, mapped_column(DateTime(timezone=True))]

# Fecha contable / de documento: DATE sin hora.
Day = Annotated[_dt.date, mapped_column(Date)]

# Moneda operativa.
Currency = Annotated[
    str, mapped_column(CHAR(3), nullable=False, server_default="COP", default="COP")
]

# Datos semiestructurados: solo respuestas DIAN y payloads de auditoria.
Json = Annotated[dict[str, Any], mapped_column(JSONB)]

# Texto libre sin limite artificial.
LongText = Annotated[str, mapped_column(Text)]


# Precisiones por defecto para tipos Python sin anotacion explicita.
type_annotation_map: dict[Any, Any] = {
    decimal.Decimal: Numeric(16, 2),
    _dt.datetime: DateTime(timezone=True),
    _dt.date: Date,
    str: String(255),
    dict[str, Any]: JSONB,
}


class Base(DeclarativeBase):
    """Base declarativa comun a todos los modelos."""

    registry = registry(
        metadata=metadata_obj,
        type_annotation_map=type_annotation_map,
    )
    metadata = metadata_obj

    def __repr__(self) -> str:  # pragma: no cover - utilidad de depuracion
        pk = getattr(self, "id", None)
        label = (
            getattr(self, "code", None)
            or getattr(self, "name", None)
            or getattr(self, "full_number", None)
            or getattr(self, "sale_number", None)
        )
        extra = f" {label!r}" if label else ""
        return f"<{type(self).__name__} id={pk}{extra}>"


# ---------------------------------------------------------------------------
# Helpers de restricciones
# ---------------------------------------------------------------------------
def enum_check(column: str, values: tuple[str, ...], *, name: str | None = None) -> CheckConstraint:
    """CHECK de dominio cerrado para una columna de estado o tipo.

    Se usa en lugar del ENUM nativo de PostgreSQL (seccion 0.2): agregar un
    valor a un ENUM exige DDL y no siempre es reversible en transaccion; un
    CHECK se recrea sin drama.
    """
    listed = ", ".join(f"'{v}'" for v in sorted(values))
    return CheckConstraint(
        f"{column} IN ({listed})",
        name=name or f"{column}_valid",
    )


def positive_check(column: str, *, allow_zero: bool = False) -> CheckConstraint:
    """CHECK de cantidad o monto no negativo."""
    op = ">=" if allow_zero else ">"
    return CheckConstraint(
        f"{column} {op} 0",
        name=f"{column}_{'non_negative' if allow_zero else 'positive'}",
    )


def fraction_check(column: str) -> CheckConstraint:
    """CHECK de porcentaje expresado como fraccion entre 0 y 1."""
    return CheckConstraint(f"{column} >= 0 AND {column} <= 1", name=f"{column}_fraction")


def validity_check() -> CheckConstraint:
    """CHECK del par de vigencia (seccion 0.5)."""
    return CheckConstraint(
        "valid_to IS NULL OR valid_to >= valid_from",
        name="validity_range",
    )


def daterange_expr(valid_from: str = "valid_from", valid_to: str = "valid_to") -> str:
    """Expresion de rango de fechas cerrada usada en las EXCLUDE de solapamiento."""
    return f"daterange({valid_from}, COALESCE({valid_to}, 'infinity'::date), '[]')"


NOW = func.now()

__all__ = [
    "Base",
    "Currency",
    "Day",
    "FK",
    "Factor",
    "Json",
    "LongText",
    "Money",
    "NAMING_CONVENTION",
    "NOW",
    "PK",
    "Percent",
    "Quantity",
    "TS",
    "UnitPrice",
    "daterange_expr",
    "enum_check",
    "fraction_check",
    "metadata_obj",
    "positive_check",
    "validity_check",
]
