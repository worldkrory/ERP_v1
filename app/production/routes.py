from flask import jsonify, render_template, request
from flask_login import login_required
from sqlalchemy.exc import SQLAlchemyError

from app.auth.decorators import audit_action, require_role

from app.production import production_bp
from app.services.production_service import (
    HistoricalPreviewValidationError,
    historical_microlot_preview,
)


@require_role("INVENTARIO", "ADMIN")
@production_bp.get("/produccion/reconstruccion-historica")
@login_required
def historical_microlot_page():
    return render_template(
        "production/historical_lot.html",
        defaults={
            "source_batch_id": 1,
            "source_location_id": 2,
            "process_id": 1,
            "executor_party_id": 22,
            "output_location_id": 2,
            "grain_product_id": 2,
            "ground_product_id": 3,
            "process_started_at": "2026-10-15",
            "process_received_at": "2026-10-20",
            "source_quantity_kg": "67.5",
            "grain_quantity": 10,
            "ground_quantity": 119,
            "grams_per_bag": "340",
            "unit_sale_price": "32000",
            "maquila_cost": "294360",
            "bags_purchase_quantity": 150,
            "bags_purchase_cost": "330000",
            "labels_cost": "165000",
            "stickers_cost": "30000",
            "freight_cost": "50000",
        },
    )


@production_bp.post("/api/v1/production/historical-microlot/preview")
@login_required
@require_role("INVENTARIO", "ADMIN")
def historical_microlot_preview_api():
    payload = request.get_json(silent=True) or {}

    try:
        preview = historical_microlot_preview(payload)
        return jsonify(preview), 200

    except HistoricalPreviewValidationError as exc:
        return jsonify({
            "valid": False,
            "error": str(exc),
        }), 400

    except SQLAlchemyError:
        return jsonify({
            "valid": False,
            "error": (
                "No fue posible consultar los datos necesarios "
                "para generar el preview."
            ),
        }), 500