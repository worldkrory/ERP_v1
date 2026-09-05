# Guía obligatoria para escribir los modelos SQLAlchemy — ERP Densa Niebla

Todos los archivos de `app/models/` deben seguir esta guía **al pie de la letra**.
No inventes columnas, tipos ni nombres: la fuente de verdad es
`/home/user/workspace/ERD_Logico_Densa_Niebla_v1.md`.

## Archivos de referencia — LÉELOS ANTES DE ESCRIBIR

- `app/models/base.py` — Base declarativa, alias de tipo, helpers de CHECK
- `app/models/mixins.py` — `TimestampMixin`, `AuditMixin`, `ActiveMixin`, `ValidityMixin`
- `app/models/user.py` — **modelo de referencia de estilo**
- `app/models/party.py` — **modelo de referencia de estilo** (el más completo)

Copia exactamente ese estilo: mismo orden de secciones, mismos comentarios en
español sin acentos en el código, mismo uso de `__table_args__`.

## Reglas duras

1. **SQLAlchemy 2.x tipado.** Siempre `Mapped[...]` + `mapped_column(...)`.
   Nunca `Column(...)` al estilo 1.x.
2. **`from __future__ import annotations`** en la primera línea de código.
3. **PK:** `id: Mapped[PK]` usando el alias de `base.py`. Nunca `Integer`.
4. **Tipos:** usa los alias de `base.py` — `Money` (16,2), `Quantity` (16,4),
   `UnitPrice` (16,4), `Factor` (20,10), `Percent` (9,6), `TS` (timestamptz),
   `Day` (date), `Currency` (char(3) default COP), `Json` (JSONB),
   `LongText` (Text). Cuando la columna es nullable declara
   `Mapped[Optional[Money]] = mapped_column(Numeric(16, 2), nullable=True)`
   con el tipo explícito, como en `party.py`.
   **Prohibido `Float`, `Double`, `REAL`.**
   **Todo `DateTime` lleva `timezone=True`.**
5. **Enums:** nunca `ENUM` nativo ni `sqlalchemy.Enum`. Declara una tupla módulo
   nivel en MAYÚSCULAS (ej. `SALE_STATUSES: tuple[str, ...] = (...)`) y aplica
   `enum_check("columna", TUPLA)` en `__table_args__`. La columna es
   `mapped_column(String(n), nullable=False)` con la longitud que dice el ERD.
   Si la columna es nullable, usa un `CheckConstraint` con
   `"col IS NULL OR col IN (...)"` como en `Party.tax_regime`.
6. **Mixins:**
   - Tabla de negocio (ERD dice "Auditoría: Completa") → `AuditMixin`
   - Tabla de catálogo (ERD dice "`created_at`, `updated_at`") → `TimestampMixin`
   - Tabla append-only sin `updated_at` (`inventory_movements`,
     `invoice_events`, `shipment_events`) → **sin mixin**, declara sus columnas
     de tiempo a mano tal como las lista el ERD
   - Si tiene `is_active` → añade `ActiveMixin` (no declares `is_active` a mano)
   - Si tiene `valid_from`/`valid_to` → añade `ValidityMixin` y pon
     `validity_check()` en `__table_args__`
   - Orden de bases: `class X(AuditMixin, ActiveMixin, Base)`
7. **ON DELETE:** copia literalmente lo que dice el ERD en cada FK. El default
   es `RESTRICT`. Nunca omitas `ondelete`.
8. **FK circulares:** cuando la FK apunte a una tabla de otro módulo que a su
   vez apunte de vuelta, añade `use_alter=True` al `ForeignKey`.
9. **Nombres de restricción:** nómbralas siempre explícitamente.
   - `UniqueConstraint(..., name="uq_<tabla>_<primera_columna>")`
   - `CheckConstraint(..., name="ck_<tabla>_<descripcion>")`
   - `Index("ix_<tabla>_<cols>", ...)` con el nombre exacto que da el ERD
     cuando el ERD lo especifica.
10. **Índices únicos parciales:** con
    `Index("nombre", "col", unique=True, postgresql_where=text("condicion"))`.
    Ver la sección 15 del ERD (líneas 2161-2221) para la lista completa.
11. **EXCLUDE de solapamiento:** usa
    `ExcludeConstraint` de `sqlalchemy.dialects.postgresql`, con
    `using="gist"`, por ejemplo:

    ```python
    ExcludeConstraint(
        ("process_id", "="),
        ("executor_party_id", "="),
        ("product_id", "="),
        (text("daterange(valid_from, COALESCE(valid_to, 'infinity'::date), '[]')"), "&&"),
        using="gist",
        name="cost_rules_no_overlap",
    )
    ```

12. **Relaciones:** declara `relationship(...)` en ambos lados con
    `back_populates`. Cabecera → detalle lleva
    `cascade="all, delete-orphan"` **solo** cuando la FK es ON DELETE CASCADE.
    Cuando hay dos FK a la misma tabla, especifica `foreign_keys=[...]`.
    Usa `TYPE_CHECKING` + comillas para las clases de otros módulos, para no
    crear importaciones circulares.
13. **`server_default`:** siempre que el ERD indique un DEFAULT, ponlo como
    `server_default` **y** `default` de Python (ver `party.py`). Booleanos:
    `server_default="true"` / `"false"`. Numéricos: `server_default="0"`.
    JSONB: `server_default="'[]'::jsonb", default=list`.
14. **Propiedades de dominio:** añade `@property` útiles y de solo lectura
    cuando aporten (ej. `is_open`, `balance_due`, `display_name`), como hace
    `party.py`. Nada de lógica de negocio pesada: eso va en `app/services/`.
15. **Docstrings en español**, sin tildes en comentarios de código (evita
    problemas de codificación en Windows). Cada clase explica en una o dos
    líneas su papel de negocio y cita la sección del ERD.
16. **`__all__`** al final de cada archivo, ordenado alfabéticamente,
    incluyendo las tuplas de constantes.
17. Las invariantes que el ERD marca como "validar en la capa de servicios"
    **no** se implementan como constraint. Déjalas documentadas en el docstring
    de la clase con el prefijo `Invariante de servicio:`.

## Qué NO hacer

- No crear tablas que no estén en el ERD.
- No renombrar columnas ni "mejorar" el diseño.
- No añadir `__init__.py` ni tocar `base.py`, `mixins.py`, `user.py`, `party.py`.
- No escribir migraciones de Alembic.
- No instalar paquetes.

## Verificación antes de terminar

```bash
cd /home/user/workspace/densa_niebla_models
python3 -c "
import sys; sys.path.insert(0,'.')
import app.models.TU_ARCHIVO as m
print('import ok:', [n for n in dir(m) if n[0].isupper()])
"
```

El chequeo completo de mapeo y DDL lo corre el orquestador al final, cuando
existan los 18 archivos. Tu responsabilidad es que tu archivo importe sin
error y que cada columna del ERD esté presente con su tipo exacto.
