from flask import jsonify, render_template, request
from flask_login import login_required
from sqlalchemy.exc import SQLAlchemyError

from app.auth.decorators import audit_action, require_role

from app.production import production_bp


from datetime import datetime
from decimal import Decimal, InvalidOperation

from app.extensions import db
from app.models.batch import Batch
from app.models.inventory import InventoryBalance, InventoryLocation
from app.models.party import Party
from app.models.product import Product
from app.models.production import (
    OUTPUT_KINDS,
    PRODUCTION_COST_TYPES,
    WASTE_COST_TREATMENTS,
    WASTE_TYPES,
    ProductionProcess,
)
from app.models.unit import UnitOfMeasure

from app.services.production_service import (
    HistoricalPreviewValidationError,
    ProductionConfirmationError,
    ProductionInputPreviewRequest,
    ProductionManualCostPreviewRequest,
    ProductionOutputPreviewRequest,
    ProductionPreviewRequest,
    ProductionPreviewValidationError,
    ProductionWastePreviewRequest,
    confirm_production,
    historical_microlot_preview,
    preview_production,
)

from flask_login import current_user
from sqlalchemy.exc import IntegrityError
from app.services.inventory_service import InventoryError



@production_bp.get("/produccion/reconstruccion-historica")
@login_required
@require_role("INVENTARIO", "ADMIN")
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

def _htmx_decimal(
    value: str | None,
    field_label: str,
    *,
    required: bool = True,
    allow_zero: bool = True,
) -> Decimal | None:
    raw_value = (value or "").strip().replace(",", ".")

    if not raw_value:
        if required:
            raise ProductionPreviewValidationError(
                f"El campo '{field_label}' es obligatorio."
            )
        return None

    try:
        result = Decimal(raw_value)
    except InvalidOperation as exc:
        raise ProductionPreviewValidationError(
            f"El campo '{field_label}' debe ser numérico."
        ) from exc

    if result < Decimal("0"):
        raise ProductionPreviewValidationError(
            f"El campo '{field_label}' no puede ser negativo."
        )

    if not allow_zero and result == Decimal("0"):
        raise ProductionPreviewValidationError(
            f"El campo '{field_label}' debe ser mayor que cero."
        )

    return result


def _htmx_optional_int(value: str | None) -> int | None:
    raw_value = (value or "").strip()

    if not raw_value:
        return None

    try:
        return int(raw_value)
    except ValueError as exc:
        raise ProductionPreviewValidationError(
            f"El valor '{raw_value}' debe ser un identificador válido."
        ) from exc


def _htmx_required_int(
    value: str | None,
    field_label: str,
) -> int:
    raw_value = (value or "").strip()

    if not raw_value:
        raise ProductionPreviewValidationError(
            f"Debes seleccionar {field_label}."
        )

    try:
        return int(raw_value)
    except ValueError as exc:
        raise ProductionPreviewValidationError(
            f"El valor de '{field_label}' no es válido."
        ) from exc


def _htmx_optional_datetime(
    value: str | None,
    field_label: str,
) -> datetime | None:
    raw_value = (value or "").strip()

    if not raw_value:
        return None

    try:
        return datetime.fromisoformat(raw_value)
    except ValueError as exc:
        raise ProductionPreviewValidationError(
            f"El campo '{field_label}' debe tener fecha y hora válida."
        ) from exc


def _active_records(model):
    query = db.session.query(model)

    if hasattr(model, "is_active"):
        query = query.filter(model.is_active.is_(True))

    return query


def _production_catalog_context() -> dict:
    return {
        "products": (
            _active_records(Product)
            .order_by(Product.name.asc())
            .all()
        ),
        "locations": (
            _active_records(InventoryLocation)
            .order_by(InventoryLocation.code.asc())
            .all()
        ),
        "processes": (
            _active_records(ProductionProcess)
            .order_by(ProductionProcess.name.asc())
            .all()
        ),
        "parties": (
            _active_records(Party)
            .order_by(Party.legal_name.asc())
            .all()
        ),
        "units": (
            _active_records(UnitOfMeasure)
            .order_by(UnitOfMeasure.code.asc())
            .all()
        ),
    }


def _form_rows(prefix: str) -> dict[int, dict[str, str]]:
    """
    Convierte campos como:

    inputs-0-product_id
    inputs-0-location_id
    outputs-1-product_id

    en un dict agrupado por índice.
    """

    rows: dict[int, dict[str, str]] = {}

    for field_name, value in request.form.items():
        if not field_name.startswith(f"{prefix}-"):
            continue

        parts = field_name.split("-", maxsplit=2)

        if len(parts) != 3:
            continue

        _, index_raw, attribute = parts

        try:
            index = int(index_raw)
        except ValueError:
            continue

        rows.setdefault(index, {})[attribute] = value

    return rows


def _parse_outputs() -> tuple[ProductionOutputPreviewRequest, ...]:
    rows = _form_rows("outputs")
    results: list[ProductionOutputPreviewRequest] = []

    for index in sorted(rows):
        row = rows[index]

        results.append(
            ProductionOutputPreviewRequest(
                product_id=_htmx_required_int(
                    row.get("product_id"),
                    f"el producto de salida #{index + 1}",
                ),
                quantity=_htmx_decimal(
                    row.get("quantity"),
                    f"la cantidad de salida #{index + 1}",
                    allow_zero=False,
                ),
                unit_id=_htmx_required_int(
                    row.get("unit_id"),
                    f"la unidad de salida #{index + 1}",
                ),
                net_weight_kg=_htmx_decimal(
                    row.get("net_weight_kg"),
                    f"el peso neto de salida #{index + 1}",
                    allow_zero=False,
                ),
                batch_code=(row.get("batch_code") or "").strip(),
                output_kind=(row.get("output_kind") or "MAIN").strip(),
                unit_sale_price=_htmx_decimal(
                    row.get("unit_sale_price"),
                    f"el precio de venta de salida #{index + 1}",
                    required=False,
                ),
                notes=(row.get("notes") or "").strip() or None,
            )
        )

    return tuple(results)


def _parse_wastes() -> tuple[ProductionWastePreviewRequest, ...]:
    rows = _form_rows("wastes")
    results: list[ProductionWastePreviewRequest] = []

    for index in sorted(rows):
        row = rows[index]

        if not (row.get("quantity") or "").strip():
            continue

        results.append(
            ProductionWastePreviewRequest(
                waste_type=(row.get("waste_type") or "PROCESS_WASTE").strip(),
                quantity=_htmx_decimal(
                    row.get("quantity"),
                    f"la cantidad de merma #{index + 1}",
                    allow_zero=False,
                ),
                unit_id=_htmx_required_int(
                    row.get("unit_id"),
                    f"la unidad de merma #{index + 1}",
                ),
                quantity_base=_htmx_decimal(
                    row.get("quantity_base"),
                    f"la cantidad base de merma #{index + 1}",
                    allow_zero=False,
                ),
                is_expected=(row.get("is_expected") or "true") == "true",
                is_recoverable=(
                    row.get("is_recoverable") or "false"
                ) == "true",
                recovered_product_id=_htmx_optional_int(
                    row.get("recovered_product_id"),
                ),
                cost_treatment=(
                    row.get("cost_treatment") or "ABSORBED_BY_OUTPUT"
                ).strip(),
                notes=(row.get("notes") or "").strip() or None,
            )
        )

    return tuple(results)


def _parse_inputs() -> tuple[ProductionInputPreviewRequest, ...]:
    rows = _form_rows("inputs")
    results: list[ProductionInputPreviewRequest] = []

    for index in sorted(rows):
        row = rows[index]

        results.append(
            ProductionInputPreviewRequest(
                product_id=_htmx_required_int(
                    row.get("product_id"),
                    f"el producto de insumo #{index + 1}",
                ),
                location_id=_htmx_required_int(
                    row.get("location_id"),
                    f"la ubicación del insumo #{index + 1}",
                ),
                quantity=_htmx_decimal(
                    row.get("quantity"),
                    f"la cantidad de insumo #{index + 1}",
                    allow_zero=False,
                ),
                unit_id=_htmx_required_int(
                    row.get("unit_id"),
                    f"la unidad del insumo #{index + 1}",
                ),
                quantity_base=_htmx_decimal(
                    row.get("quantity_base"),
                    f"la cantidad base del insumo #{index + 1}",
                    allow_zero=False,
                ),
                batch_id=_htmx_optional_int(
                    row.get("batch_id"),
                ),
                estimated_unit_cost=_htmx_decimal(
                    row.get("estimated_unit_cost"),
                    f"el costo estimado del insumo #{index + 1}",
                    required=False,
                ),
                notes=(row.get("notes") or "").strip() or None,
            )
        )

    return tuple(results)


def _parse_manual_costs() -> tuple[ProductionManualCostPreviewRequest, ...]:
    rows = _form_rows("manual_costs")
    results: list[ProductionManualCostPreviewRequest] = []

    for index in sorted(rows):
        row = rows[index]
        amount_raw = (row.get("amount") or "").strip()

        if not amount_raw:
            continue

        results.append(
            ProductionManualCostPreviewRequest(
                cost_type=(row.get("cost_type") or "").strip(),
                description=(row.get("description") or "").strip(),
                amount=_htmx_decimal(
                    amount_raw,
                    f"el monto del costo manual #{index + 1}",
                    allow_zero=False,
                ),
                supplier_party_id=_htmx_optional_int(
                    row.get("supplier_party_id"),
                ),
                supplier_document_number=(
                    row.get("supplier_document_number") or ""
                ).strip() or None,
                occurred_on=None,
                notes=(row.get("notes") or "").strip() or None,
            )
        )

    return tuple(results)

@production_bp.get("/produccion/nueva")
@login_required
@require_role("INVENTARIO", "ADMIN")
def new_production_page():
    return render_template(
        "production/new_production.html",
        **_production_catalog_context(),
    )


@production_bp.get("/produccion/partials/lotes-origen")
@login_required
@require_role("INVENTARIO", "ADMIN")
def production_source_batches_partial():
    product_id = _htmx_optional_int(request.args.get("source_product_id"))
    location_id = _htmx_optional_int(request.args.get("source_location_id"))

    balances = []

    if product_id and location_id:
        balances = (
            db.session.query(InventoryBalance)
            .join(Batch, Batch.id == InventoryBalance.batch_id)
            .filter(
                InventoryBalance.product_id == product_id,
                InventoryBalance.location_id == location_id,
                InventoryBalance.quantity_base > 0,
            )
            .order_by(Batch.batch_code.asc())
            .all()
        )

    return render_template(
        "production/partials/_source_batch_options.html",
        balances=balances,
    )


@production_bp.get("/produccion/partials/output-row")
@login_required
@require_role("INVENTARIO", "ADMIN")
def production_output_row_partial():
    row_index = int(request.args.get("index", "0"))
    

    return render_template(
        "production/partials/_output_row.html",
        row_index=row_index,
        output_kinds=OUTPUT_KINDS,
        **_production_catalog_context(),
    )


@production_bp.get("/produccion/partials/waste-row")
@login_required
@require_role("INVENTARIO", "ADMIN")
def production_waste_row_partial():
    row_index = int(request.args.get("index", "0"))

    return render_template(
    "production/partials/_waste_row.html",
    row_index=row_index,
    waste_types=WASTE_TYPES,
    cost_treatments=WASTE_COST_TREATMENTS,
    **_production_catalog_context(),
)


@production_bp.get("/produccion/partials/input-row")
@login_required
@require_role("INVENTARIO", "ADMIN")
def production_input_row_partial():
    row_index = int(request.args.get("index", "0"))
    suggested_location_id = request.args.get("location_id")

    return render_template(
        "production/partials/_input_row.html",
        row_index=row_index,
        suggested_location_id=suggested_location_id,
        **_production_catalog_context(),
    )

@production_bp.get("/produccion/partials/costo-manual-row")
@login_required
@require_role("INVENTARIO", "ADMIN")
def production_manual_cost_row_partial():
    row_index = int(request.args.get("index", "0"))

    return render_template(
        "production/partials/_manual_cost_row.html",
        row_index=row_index,
        cost_types=PRODUCTION_COST_TYPES,
        parties=(
            _active_records(Party)
            .order_by(Party.legal_name.asc())
            .all()
        ),
    )

@production_bp.get("/produccion/partials/lotes-insumo")
@login_required
@require_role("INVENTARIO", "ADMIN")
def production_input_batches_partial():
    row_index = request.args.get("row_index", "0")

    product_id = _htmx_optional_int(
        request.args.get(f"inputs-{row_index}-product_id")
    )

    location_id = _htmx_optional_int(
        request.args.get(f"inputs-{row_index}-location_id")
    )

    balances = []

    if product_id and location_id:
        balances = (
            db.session.query(InventoryBalance)
            .filter(
                InventoryBalance.product_id == product_id,
                InventoryBalance.location_id == location_id,
                InventoryBalance.quantity_base > 0,
            )
            .order_by(
                InventoryBalance.batch_id.asc(),
                InventoryBalance.id.asc(),
            )
            .all()
        )

    return render_template(
        "production/partials/_input_batch_options.html",
        row_index=row_index,
        balances=balances,
    )

def _build_production_preview_request() -> ProductionPreviewRequest:
    return ProductionPreviewRequest(
        mode=(request.form.get("mode") or "HISTORICAL").strip(),
        order_number=(request.form.get("order_number") or "").strip(),
        source_product_id=_htmx_optional_int(
            request.form.get("source_product_id"),
        ),
        source_batch_id=_htmx_optional_int(
            request.form.get("source_batch_id"),
        ),
        source_location_id=_htmx_optional_int(
            request.form.get("source_location_id"),
        ),
        source_quantity=_htmx_decimal(
            request.form.get("source_quantity"),
            "Cantidad del insumo origen",
            allow_zero=False,
        ),
        source_unit_id=_htmx_optional_int(
            request.form.get("source_unit_id"),
        ),
        source_quantity_base=_htmx_decimal(
            request.form.get("source_quantity_base"),
            "Cantidad base del insumo origen",
            allow_zero=False,
        ),
        estimated_source_unit_cost=_htmx_decimal(
            request.form.get("estimated_source_unit_cost"),
            "Costo estimado del insumo origen",
            required=False,
        ),
        process_id=_htmx_optional_int(
            request.form.get("process_id"),
        ),
        executor_party_id=_htmx_optional_int(
            request.form.get("executor_party_id"),
        ),
        processor_location_id=_htmx_optional_int(
            request.form.get("processor_location_id"),
        ),
        destination_location_id=_htmx_optional_int(
            request.form.get("destination_location_id"),
        ),
        started_at=_htmx_optional_datetime(
            request.form.get("started_at"),
            "Fecha de inicio",
        ),
        completed_at=_htmx_optional_datetime(
            request.form.get("completed_at"),
            "Fecha de terminación",
        ),
        received_at=_htmx_optional_datetime(
            request.form.get("received_at"),
            "Fecha de recepción",
        ),
        outputs=_parse_outputs(),
        wastes=_parse_wastes(),
        inputs=_parse_inputs(),
        manual_costs=_parse_manual_costs(),
        currency=(request.form.get("currency") or "COP").strip(),
        notes=(request.form.get("notes") or "").strip() or None,
        historical_reconstruction=(
            request.form.get("historical_reconstruction") == "true"
        ),
    )

@production_bp.post("/produccion/preview")
@login_required
@require_role("INVENTARIO", "ADMIN")
def production_preview_partial():
    try:
        
        preview_request = _build_production_preview_request()

        preview = preview_production(
            db.session,
            preview_request,
        )

        return render_template(
            "production/partials/_preview_result.html",
            preview=preview,
            preview_ok=True,
        )

    except (
        ValueError,
        ProductionPreviewValidationError,
    ) as exc:
        return render_template(
            "production/partials/_preview_result.html",
            preview=None,
            preview_ok=False,
            error_message=str(exc),
        ), 422

    except SQLAlchemyError:
        return render_template(
            "production/partials/_preview_result.html",
            preview=None,
            preview_ok=False,
            error_message=(
                "No fue posible consultar los saldos y costos "
                "necesarios para calcular el preview."
            ),
        ), 500

@production_bp.post("/produccion/confirmar")
@login_required
@require_role("INVENTARIO", "ADMIN")
def production_confirm_partial():
    try:
        preview_request = _build_production_preview_request()

        result = confirm_production(
            db.session,
            preview_request,
            created_by_id=current_user.id,
        )

        db.session.commit()

        return render_template(
            "production/partials/_confirmation_success.html",
            result=result,
        )

    except (
        ValueError,
        InventoryError,
        ProductionConfirmationError,
        ProductionPreviewValidationError,
    ) as exc:
        db.session.rollback()

        return render_template(
            "production/partials/_confirmation_error.html",
            error_message=str(exc),
        ), 422

    except IntegrityError:
        db.session.rollback()

        return render_template(
            "production/partials/_confirmation_error.html",
            error_message=(
                "No fue posible confirmar porque la orden o alguno "
                "de los códigos de lote ya existe. No se creó ningún "
                "movimiento de inventario."
            ),
        ), 409

    except SQLAlchemyError:
        db.session.rollback()

        return render_template(
            "production/partials/_confirmation_error.html",
            error_message=(
                "Ocurrió un error al confirmar la producción. "
                "La transacción fue revertida y no se modificó inventario."
            ),
        ), 500