"""Valida los modelos SQLAlchemy contra el ERD logico v1.0 sin necesidad de
un servidor PostgreSQL.

Que verifica:
  1. Que todos los modelos importan y que el mapeo se configura (relaciones,
     back_populates, claves foraneas resolubles).
  2. Que el DDL se puede generar con el dialecto real de PostgreSQL.
  3. Que el numero de tablas, y sus nombres, coinciden con el ERD.
  4. Que se puede resolver un orden de creacion topologico (sin ciclos duros).

Uso:  python validar_modelos.py
"""

from __future__ import annotations

import collections
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from sqlalchemy import create_mock_engine  # noqa: E402
from sqlalchemy.orm import configure_mappers  # noqa: E402
from sqlalchemy.schema import CreateTable  # noqa: E402

from app.models import Base  # noqa: E402

# 50 tablas segun la seccion 1 del ERD.
ERD_TABLES: dict[str, tuple[str, ...]] = {
    "Seguridad": ("users", "roles", "user_roles"),
    "Terceros": ("parties", "party_roles", "addresses", "party_contacts"),
    "Productos y Unidades": (
        "units_of_measure",
        "unit_conversions",
        "product_categories",
        "taxes",
        "products",
        "coffee_profiles",
    ),
    "Precios y Comisiones": (
        "price_lists",
        "price_list_items",
        "party_price_rules",
        "intermediary_fee_rules",
        "intermediary_fee_entries",
    ),
    "Compras": ("purchases", "purchase_items"),
    "Inventario y Lotes": (
        "inventory_locations",
        "batches",
        "batch_lineage",
        "inventory_movements",
        "inventory_balances",
    ),
    "Produccion": (
        "production_processes",
        "production_orders",
        "process_executions",
        "production_inputs",
        "production_outputs",
        "production_waste",
    ),
    "Costos": ("cost_categories", "cost_rules", "cost_entries"),
    "Ventas y Pagos": (
        "sales",
        "sale_items",
        "sale_item_batches",
        "payments",
        "payment_allocations",
    ),
    "Facturacion DIAN": (
        "fiscal_resolutions",
        "invoices",
        "invoice_items",
        "invoice_events",
    ),
    "Logistica": ("shipments", "shipment_items", "shipment_events"),
    "Gastos": ("expense_categories", "expenses"),
    "Configuracion": ("app_settings", "document_sequences"),
}


def main() -> int:
    errors: list[str] = []
    warnings: list[str] = []

    # 1. Mapeo -------------------------------------------------------------
    configure_mappers()
    print("[OK] Todos los mapeos se configuran sin error.")

    md = Base.metadata
    actual = set(md.tables)
    expected = {t for tables in ERD_TABLES.values() for t in tables}

    missing = sorted(expected - actual)
    extra = sorted(actual - expected)
    if missing:
        errors.append(f"Tablas del ERD que faltan ({len(missing)}): {missing}")
    if extra:
        errors.append(f"Tablas no previstas en el ERD ({len(extra)}): {extra}")

    print(f"[OK] Tablas mapeadas: {len(actual)} (ERD espera {len(expected)})")

    # 2. Convenciones ------------------------------------------------------
    for name, table in sorted(md.tables.items()):
        pk_cols = list(table.primary_key.columns)
        if not pk_cols:
            errors.append(f"{name}: sin clave primaria")
            continue
        pk = pk_cols[0]
        if pk.name != "id":
            warnings.append(f"{name}: PK se llama {pk.name!r}, no 'id'")
        if "BIGINT" not in str(pk.type).upper():
            errors.append(f"{name}: PK es {pk.type}, el ERD exige BIGINT")

        for col in table.columns:
            tname = str(col.type).upper()
            if "FLOAT" in tname or "DOUBLE" in tname or "REAL" in tname:
                errors.append(f"{name}.{col.name}: usa {col.type}; el ERD prohibe punto flotante")
            if "TIMESTAMP" in tname and "TIME ZONE" not in tname:
                errors.append(f"{name}.{col.name}: TIMESTAMP sin zona horaria")
            if col.name.endswith("_id") and col.name != "id" and not col.foreign_keys:
                # target_id de payment_allocations y cost_entries es polimorfico.
                if col.name not in {"target_id", "cost_object_id", "reference_id", "dian_track_id"}:
                    warnings.append(f"{name}.{col.name}: termina en _id pero no tiene FK")

    # 3. DDL con dialecto PostgreSQL --------------------------------------
    statements: list[str] = []

    def collect(sql, *args, **kwargs):  # noqa: ANN001
        statements.append(str(sql.compile(dialect=engine.dialect)))

    engine = create_mock_engine("postgresql+psycopg://", collect)
    md.create_all(engine, checkfirst=False)
    # SQLAlchemy no emite el punto y coma: sin el, el archivo no es ejecutable.
    ddl = "".join(s.strip() + ";\n\n" for s in statements if s.strip())
    print(f"[OK] DDL PostgreSQL generado: {len(statements)} sentencias, {len(ddl)} caracteres")

    creates = ddl.upper().count("CREATE TABLE")
    if creates != len(expected):
        errors.append(f"CREATE TABLE emitidos: {creates}, esperados {len(expected)}")

    # 3b. Nombres de restricciones ----------------------------------------
    # PostgreSQL corta los identificadores en 63 caracteres y le agrega un hash.
    # Un nombre truncado no se puede referenciar en un op.drop_constraint() de
    # Alembic, asi que un nombre demasiado largo es una bomba de tiempo.
    nombres: list[str] = []
    for t in md.tables.values():
        nombres += re.findall(r"CONSTRAINT (\S+)", str(CreateTable(t).compile(dialect=engine.dialect)))
        nombres += [i.name for i in t.indexes if i.name]
    largos = sorted({n for n in nombres if len(n) > 63}, key=len, reverse=True)
    truncados = sorted({n for n in nombres if re.search(r"_[0-9a-f]{4}$", n)})
    repetidos = {n for n, c in collections.Counter(nombres).items() if c > 1}
    if largos:
        errors.append(f"nombres de mas de 63 caracteres ({len(largos)}): {largos[:3]}")
    if truncados:
        errors.append(f"nombres truncados con hash ({len(truncados)}): {truncados[:3]}")
    if repetidos:
        errors.append(f"nombres repetidos ({len(repetidos)}): {sorted(repetidos)[:3]}")
    if not (largos or truncados or repetidos):
        print(f"[OK] {len(nombres)} nombres de restriccion e indice: unicos, "
              f"ninguno pasa de 63 caracteres (el mayor: {max(map(len, nombres))}).")

    # 4. Orden topologico de creacion -------------------------------------
    order = [t.name for t in md.sorted_tables]
    print(f"[OK] Orden de creacion resuelto para {len(order)} tablas.")
    print(f"     Primeras 12: {order[:12]}")

    # El archivo debe poder ejecutarse tal cual con psql, asi que se le anteponen
    # las extensiones (btree_gist es obligatoria: la usan las dos EXCLUDE) y se
    # envuelve en una transaccion. Si algo falla, no queda nada creado a medias.
    cabecera = (
        "-- DDL generado desde los modelos SQLAlchemy del ERP Densa Niebla.\n"
        "-- NO es una migracion de Alembic: sirve para probar el esquema en una\n"
        "-- base de datos desechable antes de aprobar los modelos.\n"
        "--\n"
        "--   createdb densa_ddl_test\n"
        "--   psql -d densa_ddl_test -f ddl_generado.sql\n"
        "\n"
        "\\set ON_ERROR_STOP on\n"
        "BEGIN;\n"
        "\n"
        "CREATE EXTENSION IF NOT EXISTS btree_gist;\n"
    )
    salida = Path(__file__).resolve().parent / "ddl_generado.sql"
    salida.write_text(cabecera + ddl + "\nCOMMIT;\n", encoding="utf-8")
    print(f"[OK] DDL escrito en {salida.name} (con extensiones y en transaccion)")

    # 5. Resultado ---------------------------------------------------------
    if warnings:
        print(f"\n--- Avisos ({len(warnings)}) ---")
        for w in warnings:
            print(f"  ! {w}")
    if errors:
        print(f"\n--- ERRORES ({len(errors)}) ---")
        for e in errors:
            print(f"  X {e}")
        return 1

    print("\nVALIDACION SUPERADA: los modelos coinciden con el ERD logico v1.0.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
