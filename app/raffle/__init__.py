from flask import Blueprint

raffle_bp = Blueprint(
    "raffle",
    __name__,
    url_prefix="/sorteo",
)

from app.raffle import routes