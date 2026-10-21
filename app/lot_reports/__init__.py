"""Reportes por lote: lista de lotes e informe administrativo y financiero de cada uno."""
from flask import Blueprint

lot_reports_bp = Blueprint("lot_reports", __name__, template_folder="templates")

from app.lot_reports import routes  # noqa: E402, F401
