from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import joinedload

from app.extensions import db
from app.models.batch import Batch
from app.models.cost import CostCategory
from app.models.inventory import InventoryBalance, InventoryLocation
from app.models.party import Party
from app.models.product import Product
from app.models.production import ProductionProcess


ZERO = Decimal("0")
ONE = Decimal("1")
HUNDRED = Decimal("100")
MONEY_QUANTUM = Decimal("0.01")
QUANTITY_QUANTUM = Decimal("0.0001")


class HistoricalPreviewValidationError(ValueError):
    """Error de validación para el preview histórico de microlote."""


@dataclass(frozen=True)
class HistoricalLotDefaults:
    source_batch_id: int = 1
    source_location_id: int = 2
    process_id: int = 1
    executor_party_id: int = 22
    output_location_id: int = 2
    grain_product_id: int = 2
    ground_product_id: int = 3
    unit_sale_price: Decimal = Decimal("32000.00")


DEFAULTS = HistoricalLotDefaults()


def _decimal(
    value: Any,
    field_name: str,
    *,
    minimum: Decimal | None = None,
    allow_zero: bool = True,
) -> Decimal:
    if value is None or str(value).strip() == "":
        raise HistoricalPreviewValidationError(
            f"El campo '{field_name}' es obligatorio."
        )

    try:
        result = Decimal(str(value).strip())
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise HistoricalPreviewValidationError(
            f"El campo '{field_name}' debe ser numérico."
        ) from exc

    if minimum is not None:
        if allow_zero and result < minimum:
            raise HistoricalPreviewValidationError(
                f"El campo '{field_name}' debe ser mayor o igual a {minimum}."
            )

        if not allow_zero and result <= minimum:
            raise HistoricalPreviewValidationError(
                f"El campo '{field_name}' debe ser mayor que {minimum}."
            )

    return result


def _integer(
    value: Any,
    field_name: str,
    *,
    minimum: int = 0,
) -> int:
    if value is None or str(value).strip() == "":
        raise HistoricalPreviewValidationError(
            f"El campo '{field_name}' es obligatorio."
        )

    try:
        result = int(value)
    except (TypeError, ValueError) as exc:
        raise HistoricalPreviewValidationError(
            f"El campo '{field_name}' debe ser un número entero."
        ) from exc

    if result < minimum:
        raise HistoricalPreviewValidationError(
            f"El campo '{field_name}' debe ser mayor o igual a {minimum}."
        )

    return result


def _date(value: Any, field_name: str) -> date:
    if value is None or str(value).strip() == "":
        raise HistoricalPreviewValidationError(
            f"El campo '{field_name}' es obligatorio."
        )

    try:
        return date.fromisoformat(str(value))
    except (TypeError, ValueError) as exc:
        raise HistoricalPreviewValidationError(
            f"El campo '{field_name}' debe tener formato AAAA-MM-DD."
        ) from exc


def _money(value: Decimal) -> Decimal:
    return value.quantize(MONEY_QUANTUM, rounding=ROUND_HALF_UP)


def _quantity(value: Decimal) -> Decimal:
    return value.quantize(QUANTITY_QUANTUM, rounding=ROUND_HALF_UP)


def _serialize_decimal(value: Decimal | None) -> str | None:
    if value is None:
        return None

    return format(value, "f")


def _serialize_date(value: date | None) -> str | None:
    return value.isoformat() if value else None


def _get_required_record(model, record_id: int, label: str):
    record = db.session.get(model, record_id)

    if record is None:
        raise HistoricalPreviewValidationError(
            f"No existe {label} con ID {record_id}."
        )

    if hasattr(record, "is_active") and not record.is_active:
        raise HistoricalPreviewValidationError(
            f"{label.capitalize()} con ID {record_id} está inactivo."
        )

    return record


def _source_balance(batch_id: int, location_id: int) -> InventoryBalance:
    statement = (
        select(InventoryBalance)
        .options(
            joinedload(InventoryBalance.batch),
            joinedload(InventoryBalance.product),
            joinedload(InventoryBalance.location),
        )
        .where(
            InventoryBalance.batch_id == batch_id,
            InventoryBalance.location_id == location_id,
        )
    )

    balance = db.session.scalar(statement)

    if balance is None:
        raise HistoricalPreviewValidationError(
            "No existe saldo de inventario para el lote origen "
            "en la ubicación seleccionada."
        )

    return balance


def _find_cost_category(code: str) -> CostCategory:
    category = db.session.scalar(
        select(CostCategory).where(
            CostCategory.code == code,
            CostCategory.is_active.is_(True),
        )
    )

    if category is None:
        raise HistoricalPreviewValidationError(
            f"No existe una categoría de costo activa con código '{code}'."
        )

    return category


def _read_default_or_payload(
    payload: dict[str, Any],
    key: str,
    default_value: int,
) -> int:
    value = payload.get(key, default_value)
    return _integer(value, key, minimum=1)


def historical_microlot_preview(payload: dict[str, Any] | None) -> dict[str, Any]:
    """
    Valida y calcula una reconstrucción histórica de microlote.

    Esta función es solo de lectura:
    - No inserta registros.
    - No actualiza inventarios.
    - No hace flush().
    - No hace commit().
    - No modifica la base de datos.
    """
    payload = payload or {}

    source_batch_id = _read_default_or_payload(
        payload,
        "source_batch_id",
        DEFAULTS.source_batch_id,
    )
    source_location_id = _read_default_or_payload(
        payload,
        "source_location_id",
        DEFAULTS.source_location_id,
    )
    process_id = _read_default_or_payload(
        payload,
        "process_id",
        DEFAULTS.process_id,
    )
    executor_party_id = _read_default_or_payload(
        payload,
        "executor_party_id",
        DEFAULTS.executor_party_id,
    )
    output_location_id = _read_default_or_payload(
        payload,
        "output_location_id",
        DEFAULTS.output_location_id,
    )

    process_started_at = _date(
        payload.get("process_started_at", "2026-10-15"),
        "process_started_at",
    )
    process_received_at = _date(
        payload.get("process_received_at", "2026-10-20"),
        "process_received_at",
    )

    if process_received_at < process_started_at:
        raise HistoricalPreviewValidationError(
            "La fecha de recepción no puede ser anterior a la fecha de inicio."
        )

    source_quantity_kg = _decimal(
        payload.get("source_quantity_kg", "67.5"),
        "source_quantity_kg",
        minimum=ZERO,
        allow_zero=False,
    )

    grain_quantity = _integer(
        payload.get("grain_quantity", 10),
        "grain_quantity",
        minimum=0,
    )
    ground_quantity = _integer(
        payload.get("ground_quantity", 119),
        "ground_quantity",
        minimum=0,
    )

    if grain_quantity + ground_quantity <= 0:
        raise HistoricalPreviewValidationError(
            "Debes registrar al menos una bolsa producida."
        )

    grams_per_bag = _decimal(
        payload.get("grams_per_bag", "340"),
        "grams_per_bag",
        minimum=ZERO,
        allow_zero=False,
    )

    unit_sale_price = _decimal(
        payload.get("unit_sale_price", str(DEFAULTS.unit_sale_price)),
        "unit_sale_price",
        minimum=ZERO,
        allow_zero=True,
    )

    maquila_cost = _decimal(
        payload.get("maquila_cost", "294360"),
        "maquila_cost",
        minimum=ZERO,
        allow_zero=True,
    )
    bags_purchase_quantity = _integer(
        payload.get("bags_purchase_quantity", 150),
        "bags_purchase_quantity",
        minimum=1,
    )
    bags_purchase_cost = _decimal(
        payload.get("bags_purchase_cost", "330000"),
        "bags_purchase_cost",
        minimum=ZERO,
        allow_zero=True,
    )
    labels_cost = _decimal(
        payload.get("labels_cost", "165000"),
        "labels_cost",
        minimum=ZERO,
        allow_zero=True,
    )
    stickers_cost = _decimal(
        payload.get("stickers_cost", "30000"),
        "stickers_cost",
        minimum=ZERO,
        allow_zero=True,
    )
    freight_cost = _decimal(
        payload.get("freight_cost", "50000"),
        "freight_cost",
        minimum=ZERO,
        allow_zero=True,
    )

    grain_product_id = _read_default_or_payload(
        payload,
        "grain_product_id",
        DEFAULTS.grain_product_id,
    )
    ground_product_id = _read_default_or_payload(
        payload,
        "ground_product_id",
        DEFAULTS.ground_product_id,
    )

    source_batch = _get_required_record(Batch, source_batch_id, "el lote")
    source_location = _get_required_record(
        InventoryLocation,
        source_location_id,
        "la ubicación origen",
    )
    output_location = _get_required_record(
        InventoryLocation,
        output_location_id,
        "la ubicación destino",
    )
    process = _get_required_record(
        ProductionProcess,
        process_id,
        "el proceso",
    )
    processor = _get_required_record(
        Party,
        executor_party_id,
        "el maquilador",
    )
    grain_product = _get_required_record(
        Product,
        grain_product_id,
        "el producto terminado en grano",
    )
    ground_product = _get_required_record(
        Product,
        ground_product_id,
        "el producto terminado molido",
    )

    if source_batch.status != "ACTIVE":
        raise HistoricalPreviewValidationError(
            f"El lote origen debe estar ACTIVE. Estado actual: {source_batch.status}."
        )

    if grain_product.product_kind != "FINISHED":
        raise HistoricalPreviewValidationError(
            "El producto en grano debe tener product_kind = FINISHED."
        )

    if ground_product.product_kind != "FINISHED":
        raise HistoricalPreviewValidationError(
            "El producto molido debe tener product_kind = FINISHED."
        )

    if not grain_product.tracks_batches or not ground_product.tracks_batches:
        raise HistoricalPreviewValidationError(
            "Los productos terminados deben tener tracks_batches = true."
        )

    source_balance = _source_balance(
        batch_id=source_batch_id,
        location_id=source_location_id,
    )

    available_quantity_base = Decimal(str(source_balance.quantity_base))
    source_unit_cost = Decimal(str(source_balance.average_unit_cost))
    available_total_value = Decimal(str(source_balance.total_value))

    if source_quantity_kg > available_quantity_base:
        raise HistoricalPreviewValidationError(
            "La cantidad de pergamino a procesar supera el saldo disponible "
            f"del lote. Disponible: {available_quantity_base}."
        )

    source_input_cost = _money(source_quantity_kg * source_unit_cost)

    total_bags = grain_quantity + ground_quantity
    net_output_grams = Decimal(total_bags) * grams_per_bag
    net_output_kg = _quantity(net_output_grams / Decimal("1000"))
    unexplained_difference_kg = _quantity(source_quantity_kg - net_output_kg)

    if unexplained_difference_kg < ZERO:
        raise HistoricalPreviewValidationError(
            "El peso empacado no puede superar el peso de pergamino procesado."
        )

    net_yield_pct = net_output_kg / source_quantity_kg

    bag_unit_cost = bags_purchase_cost / Decimal(bags_purchase_quantity)
    bags_consumed_cost = _money(bag_unit_cost * Decimal(total_bags))
    bags_remaining_quantity = bags_purchase_quantity - total_bags
    bags_remaining_cost = _money(
        bag_unit_cost * Decimal(bags_remaining_quantity)
    )

    additional_cost = _money(
        maquila_cost
        + bags_consumed_cost
        + labels_cost
        + stickers_cost
        + freight_cost
    )
    total_cost = _money(source_input_cost + additional_cost)
    cost_per_bag = total_cost / Decimal(total_bags)
    cost_per_finished_kg = total_cost / net_output_kg

    potential_revenue = _money(
        Decimal(total_bags) * unit_sale_price
    )
    potential_gross_margin = _money(
        potential_revenue - total_cost
    )
    potential_gross_margin_pct = (
        potential_gross_margin / potential_revenue
        if potential_revenue > ZERO
        else ZERO
    )

    grain_allocated_cost = _money(
        cost_per_bag * Decimal(grain_quantity)
    )
    ground_allocated_cost = _money(
        total_cost - grain_allocated_cost
    )

    grain_revenue = _money(
        Decimal(grain_quantity) * unit_sale_price
    )
    ground_revenue = _money(
        Decimal(ground_quantity) * unit_sale_price
    )

    warnings: list[str] = [
        "Preview de solo lectura: no se crearán órdenes, lotes, movimientos, costos, ventas ni pagos.",
        "Las ventas y el recaudo real aún no están registrados. La facturación mostrada es potencial, no dinero cobrado.",
        "El proceso real ocurrió en Aroma y Sabor, Dosquebradas; para esta primera reconstrucción los saldos se analizan en INV_MAN.",
        "La diferencia entre pergamino y café empacado se muestra como rendimiento neto no desagregado; no se separan trilla, tostión, muestras ni café remanente no empacado.",
    ]

    if labels_cost > ZERO:
        warnings.append(
            "Las etiquetas se asignan completamente al lote. Confirma después "
            "si sobraron etiquetas para reclasificar el costo no consumido."
        )

    if stickers_cost > ZERO:
        warnings.append(
            "Los stickers se asignan completamente al lote. Confirma después "
            "si sobraron stickers para reclasificar el costo no consumido."
        )

    if bags_remaining_quantity > 0:
        warnings.append(
            f"Quedaron {bags_remaining_quantity} bolsas sin consumir, "
            f"con valor estimado de {bags_remaining_cost} COP. "
            "Ese valor no se carga al costo del lote."
        )

    cost_categories = {
        "SERV_MAQUILA": _find_cost_category("SERV_MAQUILA"),
        "MAT_EMPAQUE_BOLSA": _find_cost_category("MAT_EMPAQUE_BOLSA"),
        "MAT_EMPAQUE_ETIQUETA": _find_cost_category("MAT_EMPAQUE_ETIQUETA"),
        "MAT_EMPAQUE_STICKER": _find_cost_category("MAT_EMPAQUE_STICKER"),
        "FLETE_CAFE": _find_cost_category("FLETE_CAFE"),
    }

    return {
        "valid": True,
        "mode": "READ_ONLY_PREVIEW",
        "historical_process": {
            "process_id": process.id,
            "process_code": process.code,
            "process_name": process.name,
            "executor_party_id": processor.id,
            "executor_name": processor.legal_name,
            "executor_type": "EXTERNAL",
            "started_at": _serialize_date(process_started_at),
            "received_at": _serialize_date(process_received_at),
            "duration_days": (process_received_at - process_started_at).days,
            "notes": (
                "Aroma y Sabor, Dosquebradas. Maquila integral histórica: "
                "trilla, clasificación, tostión media, molienda opcional y empaque."
            ),
        },
        "source_batch": {
            "id": source_batch.id,
            "source_batch_id": source_batch.batch_code,
            "status": source_batch.status,
            "product_id": source_batch.product_id,
            "product_name": (
                source_balance.product.name
                if source_balance.product is not None
                else None
            ),
            "location_id": source_location.id,
            "location_code": source_location.code,
            "location_name": source_location.name,
            "available_quantity_base": _serialize_decimal(
                _quantity(available_quantity_base)
            ),
            "processed_quantity_kg": _serialize_decimal(
                _quantity(source_quantity_kg)
            ),
            "unit_cost": _serialize_decimal(source_unit_cost),
            "available_total_value": _serialize_decimal(
                _money(available_total_value)
            ),
            "input_cost_assigned": _serialize_decimal(source_input_cost),
        },
        "production": {
            "grain_bags": grain_quantity,
            "ground_bags": ground_quantity,
            "total_bags": total_bags,
            "grams_per_bag": _serialize_decimal(grams_per_bag),
            "net_output_grams": _serialize_decimal(
                _quantity(net_output_grams)
            ),
            "net_output_kg": _serialize_decimal(net_output_kg),
            "input_kg": _serialize_decimal(_quantity(source_quantity_kg)),
            "unexplained_difference_kg": _serialize_decimal(
                unexplained_difference_kg
            ),
            "net_yield_pct": _serialize_decimal(net_yield_pct),
            "net_yield_display": (
                f"{(net_yield_pct * HUNDRED).quantize(Decimal('0.01'))}%"
            ),
        },
        "costs": {
            "coffee_input_cost": _serialize_decimal(source_input_cost),
            "maquila_cost": _serialize_decimal(_money(maquila_cost)),
            "bags_purchase_quantity": bags_purchase_quantity,
            "bags_purchase_cost": _serialize_decimal(
                _money(bags_purchase_cost)
            ),
            "bags_unit_cost": _serialize_decimal(_money(bag_unit_cost)),
            "bags_consumed_quantity": total_bags,
            "bags_consumed_cost": _serialize_decimal(bags_consumed_cost),
            "bags_remaining_quantity": bags_remaining_quantity,
            "bags_remaining_cost": _serialize_decimal(bags_remaining_cost),
            "labels_cost": _serialize_decimal(_money(labels_cost)),
            "stickers_cost": _serialize_decimal(_money(stickers_cost)),
            "freight_cost": _serialize_decimal(_money(freight_cost)),
            "additional_cost": _serialize_decimal(additional_cost),
            "total_cost": _serialize_decimal(total_cost),
            "cost_per_bag": _serialize_decimal(cost_per_bag),
            "cost_per_finished_kg": _serialize_decimal(cost_per_finished_kg),
            "categories": {
                code: {
                    "id": category.id,
                    "code": category.code,
                    "name": category.name,
                }
                for code, category in cost_categories.items()
            },
        },
        "commercial_projection": {
            "unit_sale_price": _serialize_decimal(_money(unit_sale_price)),
            "potential_revenue": _serialize_decimal(potential_revenue),
            "potential_gross_margin": _serialize_decimal(
                potential_gross_margin
            ),
            "potential_gross_margin_pct": _serialize_decimal(
                potential_gross_margin_pct
            ),
            "potential_gross_margin_display": (
                f"{(potential_gross_margin_pct * HUNDRED).quantize(Decimal('0.01'))}%"
            ),
            "break_even_price_per_bag": _serialize_decimal(cost_per_bag),
        },
        "outputs": [
            {
                "product_id": grain_product.id,
                "product_name": grain_product.name,
                "sku": grain_product.sku,
                "presentation": "340 g en grano",
                "quantity": grain_quantity,
                "net_weight_kg": _serialize_decimal(
                    _quantity(Decimal(grain_quantity) * grams_per_bag / Decimal("1000"))
                ),
                "allocated_cost": _serialize_decimal(grain_allocated_cost),
                "unit_cost": _serialize_decimal(cost_per_bag),
                "unit_sale_price": _serialize_decimal(_money(unit_sale_price)),
                "potential_revenue": _serialize_decimal(grain_revenue),
                "potential_gross_margin": _serialize_decimal(
                    _money(grain_revenue - grain_allocated_cost)
                ),
            },
            {
                "product_id": ground_product.id,
                "product_name": ground_product.name,
                "sku": ground_product.sku,
                "presentation": "340 g molido",
                "quantity": ground_quantity,
                "net_weight_kg": _serialize_decimal(
                    _quantity(Decimal(ground_quantity) * grams_per_bag / Decimal("1000"))
                ),
                "allocated_cost": _serialize_decimal(ground_allocated_cost),
                "unit_cost": _serialize_decimal(cost_per_bag),
                "unit_sale_price": _serialize_decimal(_money(unit_sale_price)),
                "potential_revenue": _serialize_decimal(ground_revenue),
                "potential_gross_margin": _serialize_decimal(
                    _money(ground_revenue - ground_allocated_cost)
                ),
            },
        ],
        "warnings": warnings,
    }