r"""Ejecuta el DDL contra un PostgreSQL real, en una base de datos desechable.

Esta es la unica verificacion que no se pudo hacer al escribir los modelos: que
PostgreSQL acepte de verdad las 209 expresiones CHECK y las 2 restricciones
EXCLUDE. SQLAlchemy compila esas cadenas sin analizarlas, asi que solo el motor
puede confirmarlas.

Crea una base temporal, corre el DDL, cuenta lo creado, y la borra siempre —
incluso si algo falla. No toca densa_niebla_dev ni Alembic.

Uso:
    python probar_ddl_postgres.py

Toma la conexion de DEV_DATABASE_URL o DATABASE_URL del entorno (.env incluido)
y solo le cambia el nombre de la base. Si prefieres indicarla a mano:

    python probar_ddl_postgres.py postgresql+psycopg://postgres:clave@localhost:5432/postgres
"""
from __future__ import annotations

import os
import sys
import traceback
from pathlib import Path

AQUI = Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI))

from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

BASE_PRUEBA = "densa_ddl_test"


def cargar_dotenv() -> None:
    """Lee .env si existe, sin exigir python-dotenv."""
    for nombre in (".env", ".env.dev"):
        ruta = AQUI / nombre
        if not ruta.is_file():
            ruta = AQUI.parent / nombre
        if not ruta.is_file():
            continue
        for linea in ruta.read_text(encoding="utf-8").splitlines():
            linea = linea.strip()
            if not linea or linea.startswith("#") or "=" not in linea:
                continue
            clave, _, valor = linea.partition("=")
            os.environ.setdefault(clave.strip(), valor.strip().strip("\"'"))


def resolver_url():
    if len(sys.argv) > 1:
        return make_url(sys.argv[1])
    cargar_dotenv()
    for var in ("DEV_DATABASE_URL", "DATABASE_URL"):
        crudo = os.environ.get(var)
        if crudo:
            # Heroku entrega postgres://, que SQLAlchemy 2.x ya no acepta.
            if crudo.startswith("postgres://"):
                crudo = crudo.replace("postgres://", "postgresql+psycopg://", 1)
            print(f"Conexion tomada de {var}")
            return make_url(crudo)
    sys.exit(
        "[ERROR] No encontre DEV_DATABASE_URL ni DATABASE_URL.\n"
        "        Pasa la conexion como argumento:\n"
        "        python probar_ddl_postgres.py "
        "postgresql+psycopg://postgres:clave@localhost:5432/postgres"
    )


def main() -> int:
    ddl_path = AQUI / "ddl_generado.sql"
    if not ddl_path.is_file():
        sys.exit("[ERROR] Falta ddl_generado.sql. Corre primero validar_modelos.py")
    ddl = ddl_path.read_text(encoding="utf-8")
    # psql entiende \set; el driver no. Se quita solo esa linea.
    ddl = "\n".join(l for l in ddl.splitlines() if not l.startswith("\\set"))

    url = resolver_url()
    if url.password in ("TU_CLAVE", "clave", "tu_clave", "PASSWORD"):
        sys.exit(
            f"[ERROR] '{url.password}' es el texto de ejemplo, no una contrasena.\n"
            "        Reemplazalo por la clave real de tu servidor, o mejor: corre\n"
            "        el script sin argumentos y deja que lea el .env.\n\n"
            "            python probar_ddl_postgres.py"
        )
    url_admin = url.set(database="postgres")
    url_prueba = url.set(database=BASE_PRUEBA)
    print(f"Servidor: {url_admin.host}:{url_admin.port or 5432} como {url_admin.username}")

    admin = create_engine(url_admin, isolation_level="AUTOCOMMIT")
    try:
        with admin.connect() as cx:
            version = cx.execute(text("SHOW server_version")).scalar()
            print(f"PostgreSQL {version}")
            cx.execute(text(f'DROP DATABASE IF EXISTS "{BASE_PRUEBA}"'))
            cx.execute(text(f'CREATE DATABASE "{BASE_PRUEBA}"'))
            print(f"[OK] Base desechable {BASE_PRUEBA} creada.")
    except Exception as e:
        msg = str(e).lower()
        # Distinguir los tres fallos de conexion: son problemas muy distintos.
        if "autentificaci" in msg or "authentication" in msg or "password" in msg:
            print(f"\n[ERROR] El servidor respondio, pero rechazo la contrasena de "
                  f"'{url_admin.username}'.")
            print("        PostgreSQL SI esta corriendo: el problema es solo la clave.\n")
            print("        Averigua la clave buena:   psql -U postgres")
            print("        O usa la del .env:         python probar_ddl_postgres.py")
        elif "refused" in msg or "rechaz" in msg or "no se pudo conectar" in msg:
            print("\n[ERROR] Nadie contesta en "
                  f"{url_admin.host}:{url_admin.port or 5432}.")
            print("        El servidor esta apagado o escucha en otro puerto.\n")
            print("        Revisalo con:   Get-Service postgresql*")
            print("        Y arrancalo:    Start-Service postgresql-x64-16")
        elif "permission denied to create database" in msg or "permiso denegado" in msg:
            print(f"\n[ERROR] '{url_admin.username}' no tiene permiso para crear bases.")
            print("        Usa un usuario con CREATEDB, por ejemplo postgres.")
        else:
            print("\n[ERROR] Fallo la conexion al servidor. Detalle:\n")
            traceback.print_exc(limit=1)
        return 1

    fallo = False
    motor = create_engine(url_prueba)
    try:
        with motor.begin() as cx:
            # exec_driver_sql pasa el SQL al driver sin que SQLAlchemy lo analice.
            cx.exec_driver_sql(ddl)
        print("[OK] El DDL se ejecuto completo, sin errores de PostgreSQL.")

        with motor.connect() as cx:
            q = lambda s: cx.execute(text(s)).scalar()
            tablas = q("SELECT count(*) FROM information_schema.tables "
                       "WHERE table_schema='public' AND table_type='BASE TABLE'")
            checks = q("SELECT count(*) FROM pg_constraint WHERE contype='c' "
                       "AND connamespace='public'::regnamespace")
            fks = q("SELECT count(*) FROM pg_constraint WHERE contype='f' "
                    "AND connamespace='public'::regnamespace")
            uniques = q("SELECT count(*) FROM pg_constraint WHERE contype='u' "
                        "AND connamespace='public'::regnamespace")
            excl = q("SELECT count(*) FROM pg_constraint WHERE contype='x' "
                     "AND connamespace='public'::regnamespace")
            indices = q("SELECT count(*) FROM pg_indexes WHERE schemaname='public'")
            print(f"\n  tablas   : {tablas:>4}   (esperadas 50)")
            print(f"  CHECK    : {checks:>4}")
            print(f"  FK       : {fks:>4}")
            print(f"  UNIQUE   : {uniques:>4}")
            print(f"  EXCLUDE  : {excl:>4}   (esperadas 2)")
            print(f"  indices  : {indices:>4}")

            if tablas != 50:
                print(f"\n[ERROR] Se crearon {tablas} tablas, no 50.")
                fallo = True
            if excl != 2:
                print(f"\n[ERROR] Se crearon {excl} restricciones EXCLUDE, no 2.")
                fallo = True

            # Prueba viva: las EXCLUDE deben rechazar un solapamiento real.
            print("\nProbando que las EXCLUDE realmente bloqueen solapamientos...")
            try:
                # Solo columnas obligatorias sin default; el resto lo pone la BD.
                cx.execute(text(
                    "INSERT INTO units_of_measure (code, name, dimension) "
                    "VALUES ('LB','Libra','MASS')"))
                cx.execute(text(
                    "INSERT INTO price_lists (code, name, channel, valid_from) "
                    "VALUES ('GEN','General','RETAIL','2026-01-01')"))
                cx.execute(text(
                    "INSERT INTO products (sku, name, product_kind, base_unit_id, "
                    "costing_method) VALUES "
                    "('P1','Cafe','FINISHED_GOOD',1,'WEIGHTED_AVERAGE')"))
                # min_quantity default 0 en ambas filas -> los rangos de cantidad
                # se solapan; las vigencias tambien. Debe saltar la EXCLUDE.
                ins = ("INSERT INTO price_list_items (price_list_id, product_id, "
                       "unit_id, unit_price, valid_from, valid_to) VALUES "
                       "(1,1,1,{p},'2026-01-01','{fin}')")
                cx.execute(text(ins.format(p=6000, fin="2026-06-30")))
                try:
                    cx.execute(text(ins.format(p=7000, fin="2026-12-31")))
                    print("[ERROR] PostgreSQL acepto dos precios solapados. "
                          "La EXCLUDE no esta funcionando.")
                    fallo = True
                except Exception as e:
                    if "price_list_items_no_overlap" in str(e):
                        print("[OK] El solapamiento de precios fue rechazado "
                              "por price_list_items_no_overlap.")
                    else:
                        print(f"[?] Rechazado, pero por otra causa: {str(e)[:200]}")
            except Exception as e:
                print(f"[?] No pude montar el caso de prueba: {str(e)[:300]}")
            cx.rollback()
    except Exception:
        print("\n[ERROR] PostgreSQL rechazo el DDL. Este es el detalle:\n")
        traceback.print_exc(limit=3)
        fallo = True
    finally:
        motor.dispose()
        with admin.connect() as cx:
            cx.execute(text(f'DROP DATABASE IF EXISTS "{BASE_PRUEBA}"'))
        print(f"\n[OK] Base desechable {BASE_PRUEBA} eliminada.")
        admin.dispose()

    if fallo:
        print("\nPRUEBA FALLIDA: el esquema no se puede crear tal como esta.")
        return 1
    print("\nPRUEBA SUPERADA: PostgreSQL acepta el esquema completo.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
