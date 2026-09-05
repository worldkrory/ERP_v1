"""Módulo de autenticación y autorización del ERP Densa Niebla.

Gestiona:
- Login/logout de usuarios
- Validación de credenciales
- Control de acceso por roles
- Auditoría de accesos
"""

from flask import Blueprint

auth_bp = Blueprint(
    "auth",
    __name__,
    url_prefix="/auth",
    template_folder="templates",
)

from app.auth import routes  # noqa: E402, F401

__all__ = ["auth_bp"]
