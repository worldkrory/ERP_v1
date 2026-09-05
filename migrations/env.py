from __future__ import annotations

import logging
from logging.config import fileConfig

from alembic import context
from flask import current_app

config = context.config
fileConfig(config.config_file_name)
logger = logging.getLogger("alembic.env")


def get_engine():
    migrate = current_app.extensions["migrate"]
    try:  # Flask-SQLAlchemy < 3 y Alchemical
        return migrate.db.get_engine()
    except (TypeError, AttributeError):  # Flask-SQLAlchemy >= 3
        return migrate.db.engine


def get_engine_url() -> str:
    """URL sin la contrasena: este valor termina en los logs de Alembic."""
    try:
        return get_engine().url.render_as_string(hide_password=True).replace("%", "%%")
    except AttributeError:
        return str(get_engine().url).replace("%", "%%")


config.set_main_option("sqlalchemy.url", get_engine_url())
target_db = current_app.extensions["migrate"].db


def get_metadata():
    if hasattr(target_db, "metadatas"):
        return target_db.metadatas[None]
    return target_db.metadata


def run_migrations_offline() -> None:
    """Genera el SQL sin conectarse. Util para revisar antes de aplicar."""
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=get_metadata(),
        literal_binds=True,
        compare_type=True,
        compare_server_default=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    def process_revision_directives(ctx, revision, directives):
        """No crear archivos de migracion vacios."""
        if getattr(config.cmd_opts, "autogenerate", False):
            script = directives[0]
            if script.upgrade_ops.is_empty():
                directives[:] = []
                logger.info("Sin cambios en el esquema: no se genero migracion.")

    # Flask-Migrate ya trae sus propios valores aqui (entre ellos compare_type),
    # asi que hay que ESCRIBIR en este diccionario y no pasar los mismos
    # argumentos por separado a configure(): llegarian duplicados y falla con
    # "got multiple values for keyword argument".
    conf_args = dict(current_app.extensions["migrate"].configure_args)
    if conf_args.get("process_revision_directives") is None:
        conf_args["process_revision_directives"] = process_revision_directives
    # Los dos que importan: detectar cambios de tipo y de DEFAULT. Se forzan
    # porque compare_server_default viene en False por omision.
    conf_args["compare_type"] = True
    conf_args["compare_server_default"] = True

    connectable = get_engine()
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=get_metadata(),
            **conf_args,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()