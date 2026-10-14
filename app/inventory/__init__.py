from flask import Blueprint

inventory_admin_bp = Blueprint(
    "inventory_admin", __name__, template_folder="templates"
)

from app.inventory import routes  # noqa: E402, F401
