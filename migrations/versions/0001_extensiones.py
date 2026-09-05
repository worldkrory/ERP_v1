"""Extensiones de PostgreSQL requeridas por el esquema.

Va sola y va primera. btree_gist es obligatoria: sin ella, las restricciones
EXCLUDE de price_list_items y cost_rules no se pueden crear, y son las que
impiden que dos precios o dos costos se solapen en el tiempo.

Alembic no genera esto por autogenerate — las extensiones no forman parte del
metadata — asi que es la unica migracion escrita a mano.

Sobre el esquema de instalacion: Heroku Postgres no permite instalar extensiones
en `public` y exige el esquema `heroku_ext`. Un CREATE EXTENSION fijo en `public`
funcionaria en local y fallaria al desplegar, asi que aqui se detecta el entorno
en tiempo de ejecucion y la misma migracion sirve para los dos.

Revision ID: 0001_extensiones
Revises: (ninguna, es la primera)
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0001_extensiones"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()

    ya_instalada = conn.execute(sa.text(
        "SELECT 1 FROM pg_extension WHERE extname = 'btree_gist'"
    )).scalar()
    if ya_instalada:
        # Caso normal si un administrador la instalo a mano porque el usuario de
        # la aplicacion no tiene permiso para CREATE EXTENSION.
        print("btree_gist ya estaba instalada: no se hace nada.")
        return

    hay_heroku_ext = conn.execute(sa.text(
        "SELECT 1 FROM information_schema.schemata "
        "WHERE schema_name = 'heroku_ext'"
    )).scalar()

    if hay_heroku_ext:
        print("Instalando btree_gist en el esquema heroku_ext.")
        op.execute("CREATE EXTENSION IF NOT EXISTS btree_gist WITH SCHEMA heroku_ext")
    else:
        print("Instalando btree_gist en el esquema public.")
        op.execute("CREATE EXTENSION IF NOT EXISTS btree_gist")


def downgrade() -> None:
    # Solo se elimina si ninguna tabla la usa todavia; si el esquema existe,
    # PostgreSQL lo impide y eso es lo correcto. Por eso no se usa CASCADE:
    # un CASCADE aqui borraria en silencio las dos restricciones EXCLUDE.
    op.execute("DROP EXTENSION IF EXISTS btree_gist")
