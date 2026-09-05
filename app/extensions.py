"""Extensiones Flask del ERP Densa Niebla.

Punto unico de instanciacion. Ninguna extension recibe la app aqui: eso ocurre
en ``create_app`` mediante ``init_app``, para no acoplar el modulo a una
configuracion concreta.

Nota sobre ``db``: se construye con ``model_class=Base`` (patron de
Flask-SQLAlchemy 3.1+). Asi los modelos de ``app/models/`` son SQLAlchemy 2.x
puro y se pueden importar, validar y usar con Alembic sin necesidad de una
aplicacion Flask viva.
"""

from __future__ import annotations

from flask_login import LoginManager
from flask_migrate import Migrate
from flask_sqlalchemy import SQLAlchemy

from app.models.base import Base

db = SQLAlchemy(model_class=Base)
migrate = Migrate()
login_manager = LoginManager()

login_manager.login_view = "auth.login"
login_manager.login_message = "Inicia sesion para continuar."
login_manager.login_message_category = "warning"
login_manager.session_protection = "strong"


@login_manager.user_loader
def load_user(user_id: str):  # noqa: ANN201
    """Carga el usuario de la sesion. Solo usuarios activos y no bloqueados."""
    from app.models.user import User

    user = db.session.get(User, int(user_id))
    if user is None or not user.is_active or user.is_locked:
        return None
    return user


__all__ = ["db", "login_manager", "migrate"]
