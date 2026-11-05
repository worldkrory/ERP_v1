from flask import Blueprint
maquila_bp = Blueprint("maquila", __name__)
from app.maquila import routes
