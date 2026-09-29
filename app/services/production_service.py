from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any, Literal, Sequence

from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload

from app.extensions import db
from app.models.batch import Batch, BatchLineage
from app.models.cost import CostCategory
from app.models.inventory import InventoryBalance, InventoryLocation
from app.models.party import Party
from app.models.product import Product
from app.models.production import (
    PRODUCTION_COST_TYPES,
    WASTE_COST_TREATMENTS,
    WASTE_TYPES,
    ProductionProcess,
    ProcessExecution,
    ProductionCost,
    ProductionInput,
    ProductionOrder,
    ProductionOutput,
    ProductionWaste,
)

###

from app.services.inventory_service import (
    get_available_quantity,
    InventoryError,
    create_production_input_movement,
    create_production_output_movement,
)


ZERO = Decimal("0")
ONE = Decimal("1")
HUNDRED = Decimal("100")
MONEY_QUANTUM = Decimal("0.01")
QUANTITY_QUANTUM = Decimal("0.0001")
PERCENT_QUANTUM = Decimal("0.000001")


class HistoricalPreviewValidationError(ValueError):
    """Error de validación para el preview histórico de microlote."""

class ProductionPreviewValidationError(ValueError):
    """Error de validación para previews genéricos de producción."""

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

ProductionPreviewMode = Literal["REAL", "HISTORICAL", "SIMULATION"]


@dataclass(frozen=True)
class ProductionOutputPreviewRequest:
    """Producto terminado o subproducto a evaluar en un preview."""

    product_id: int
    quantity: Decimal
    unit_id: int
    net_weight_kg: Decimal
    batch_code: str
    output_kind: str = "MAIN"
    unit_sale_price: Decimal | None = None
    notes: str | None = None


@dataclass(frozen=True)
class ProductionWastePreviewRequest:
    """Merma registrada o estimada en un preview."""

    waste_type: str
    quantity: Decimal
    unit_id: int
    quantity_base: Decimal
    is_expected: bool = True
    is_recoverable: bool = False
    recovered_product_id: int | None = None
    cost_treatment: str = "ABSORBED_BY_OUTPUT"
    notes: str | None = None


@dataclass(frozen=True)
class ProductionManualCostPreviewRequest:
    """Costo no inventariable manual de una corrida o simulación."""

    cost_type: str
    description: str
    amount: Decimal
    supplier_party_id: int | None = None
    supplier_document_number: str | None = None
    occurred_on: date | None = None
    notes: str | None = None


@dataclass(frozen=True)
class ProductionInputPreviewRequest:
    """Insumo físico usado para preview, como bolsa, etiqueta o sticker."""

    product_id: int
    location_id: int
    quantity: Decimal
    unit_id: int
    quantity_base: Decimal
    batch_id: int | None = None
    estimated_unit_cost: Decimal | None = None
    notes: str | None = None


@dataclass(frozen=True)
class ProductionPreviewRequest:
    """Solicitud de cálculo de producción sin persistencia."""

    mode: ProductionPreviewMode
    order_number: str

    source_product_id: int | None
    source_batch_id: int | None
    source_location_id: int | None
    source_quantity: Decimal
    source_unit_id: int | None
    source_quantity_base: Decimal
    estimated_source_unit_cost: Decimal | None = None

    process_id: int | None = None
    executor_party_id: int | None = None
    processor_location_id: int | None = None
    destination_location_id: int | None = None

    started_at: datetime | None = None
    completed_at: datetime | None = None
    received_at: datetime | None = None

    outputs: tuple[ProductionOutputPreviewRequest, ...] = ()
    wastes: tuple[ProductionWastePreviewRequest, ...] = ()
    inputs: tuple[ProductionInputPreviewRequest, ...] = ()
    manual_costs: tuple[ProductionManualCostPreviewRequest, ...] = ()

    currency: str = "COP"
    notes: str | None = None
    historical_reconstruction: bool = False


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

def _preview_decimal(
    value: Any,
    field_name: str,
    *,
    allow_zero: bool = True,
) -> Decimal:
    """Convertir un valor a Decimal para previews genéricos."""

    if value is None or str(value).strip() == "":
        raise ProductionPreviewValidationError(
            f"El campo '{field_name}' es obligatorio."
        )

    try:
        result = Decimal(str(value).strip())
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ProductionPreviewValidationError(
            f"El campo '{field_name}' debe ser numérico."
        ) from exc

    if result < ZERO or (not allow_zero and result <= ZERO):
        expected = "mayor o igual a cero" if allow_zero else "mayor que cero"
        raise ProductionPreviewValidationError(
            f"El campo '{field_name}' debe ser {expected}."
        )

    return result


def _preview_required_record(
    session: Session,
    model: type,
    record_id: int | None,
    label: str,
):
    """Cargar un registro requerido desde la sesión entregada."""

    if record_id is None:
        raise ProductionPreviewValidationError(
            f"Debes seleccionar {label}."
        )

    record = session.get(model, record_id)

    if record is None:
        raise ProductionPreviewValidationError(
            f"No existe {label} con ID {record_id}."
        )

    if hasattr(record, "is_active") and not record.is_active:
        raise ProductionPreviewValidationError(
            f"{label.capitalize()} con ID {record_id} está inactivo."
        )

    return record


def _preview_source_balance(
    session: Session,
    *,
    product_id: int,
    batch_id: int,
    location_id: int,
) -> InventoryBalance:
    """Buscar saldo de lote origen para preview REAL/HISTORICAL."""

    balance = session.scalar(
        select(InventoryBalance)
        .options(
            joinedload(InventoryBalance.batch),
            joinedload(InventoryBalance.product),
            joinedload(InventoryBalance.location),
        )
        .where(
            InventoryBalance.product_id == product_id,
            InventoryBalance.batch_id == batch_id,
            InventoryBalance.location_id == location_id,
        )
    )

    if balance is None:
        raise ProductionPreviewValidationError(
            "No existe saldo para el producto, lote y ubicación origen."
        )

    return balance


def _validate_output_product(product: Product) -> None:
    """Comprobar que un producto pueda salir de producción."""

    if product.product_kind != "FINISHED":
        raise ProductionPreviewValidationError(
            f"El producto '{product.name}' debe ser FINISHED."
        )

    if not product.is_produced:
        raise ProductionPreviewValidationError(
            f"El producto '{product.name}' debe tener is_produced = true."
        )

    if not product.tracks_batches:
        raise ProductionPreviewValidationError(
            f"El producto '{product.name}' debe manejar lotes."
        )


def _safe_ratio(numerator: Decimal, denominator: Decimal) -> Decimal:
    """Dividir de forma segura para rendimiento y distribución."""

    return numerator / denominator if denominator > ZERO else ZERO


def _preview_warnings(
    request: ProductionPreviewRequest,
    *,
    unexplained_difference_kg: Decimal,
) -> list[str]:
    """Construir advertencias no bloqueantes para el preview."""

    warnings = [
        "Preview de solo lectura: no se crearán órdenes, lotes, "
        "movimientos, costos ni saldos de inventario.",
    ]

    if request.mode == "HISTORICAL":
        warnings.append(
            "Reconstrucción histórica: revisa cantidades, fechas y costos "
            "antes de confirmar la operación."
        )

    if request.mode == "SIMULATION":
        warnings.append(
            "Simulación: los costos y resultados son estimados; no se "
            "creará compra ni se reservará inventario."
        )

    if unexplained_difference_kg > Decimal("0.0001"):
        warnings.append(
            "Existe una diferencia pendiente de clasificar. Regístrala como "
            "MERMA_PROCESO u otra merma antes de confirmar una producción real."
        )

    return warnings


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

def preview_production(
    session: Session,
    request: ProductionPreviewRequest,
) -> dict[str, Any]:
    """Calcular un preview de producción para cualquier lote.

    Modos:
    - REAL: valida lote y saldo disponible actuales.
    - HISTORICAL: usa lote existente, admite fechas/costos históricos.
    - SIMULATION: permite estimar costo/rendimiento sin crear ni consumir datos.

    Esta función no inserta, actualiza, hace flush ni commit.
    """

    if request.mode not in ("REAL", "HISTORICAL", "SIMULATION"):
        raise ProductionPreviewValidationError(
            "El modo de producción no es válido."
        )

    if not request.order_number or not request.order_number.strip():
        raise ProductionPreviewValidationError(
            "Debes ingresar un número de orden."
        )

    if not request.outputs:
        raise ProductionPreviewValidationError(
            "Debes registrar al menos un producto de salida."
        )

    source_product = None
    source_batch = None
    source_location = None
    source_balance = None
    source_unit_cost = ZERO

    if request.mode != "SIMULATION":
        source_product = _preview_required_record(
            session,
            Product,
            request.source_product_id,
            "el producto origen",
        )
        source_batch = _preview_required_record(
            session,
            Batch,
            request.source_batch_id,
            "el lote origen",
        )
        source_location = _preview_required_record(
            session,
            InventoryLocation,
            request.source_location_id,
            "la ubicación origen",
        )

        if source_batch.product_id != source_product.id:
            raise ProductionPreviewValidationError(
                "El lote origen no pertenece al producto origen."
            )

        source_balance = _preview_source_balance(
            session,
            product_id=source_product.id,
            batch_id=source_batch.id,
            location_id=source_location.id,
        )

        source_unit_cost = Decimal(source_balance.average_unit_cost)

    process = None
    executor = None
    processor_location = None
    destination_location = None

    if request.process_id is not None:
        process = _preview_required_record(
            session,
            ProductionProcess,
            request.process_id,
            "el proceso",
        )

    if request.executor_party_id is not None:
        executor = _preview_required_record(
            session,
            Party,
            request.executor_party_id,
            "el ejecutor",
        )

    if request.processor_location_id is not None:
        processor_location = _preview_required_record(
            session,
            InventoryLocation,
            request.processor_location_id,
            "la ubicación del procesador",
        )

    if request.destination_location_id is not None:
        destination_location = _preview_required_record(
            session,
            InventoryLocation,
            request.destination_location_id,
            "la ubicación destino",
        )

    if request.mode == "REAL":
        if process is None:
            raise ProductionPreviewValidationError(
                "La producción REAL necesita proceso."
            )

        if executor is None:
            raise ProductionPreviewValidationError(
                "La producción REAL necesita ejecutor."
            )

        if processor_location is None:
            raise ProductionPreviewValidationError(
                "La producción REAL necesita ubicación del procesador."
            )

        if destination_location is None:
            raise ProductionPreviewValidationError(
                "La producción REAL necesita ubicación destino."
            )

    source_quantity_base = _preview_decimal(
        request.source_quantity_base,
        "cantidad base del insumo origen",
        allow_zero=False,
    )

    if source_balance is not None:
        available_source = Decimal(source_balance.quantity_base)

        if request.mode == "REAL" and source_quantity_base > available_source:
            raise ProductionPreviewValidationError(
                "La cantidad a procesar supera el saldo del lote origen."
            )

        source_input_cost = _money(
            source_quantity_base * source_unit_cost
        )
    else:
        source_unit_cost = _preview_decimal(
            request.estimated_source_unit_cost,
            "costo unitario estimado del insumo",
            allow_zero=True,
        )
        source_input_cost = _money(
            source_quantity_base * source_unit_cost
        )

    serialized_outputs: list[dict[str, Any]] = []
    output_weight_kg = ZERO
    total_finished_units = ZERO

    for output in request.outputs:
        product = _preview_required_record(
            session,
            Product,
            output.product_id,
            "un producto de salida",
        )
        _validate_output_product(product)

        quantity = _preview_decimal(
            output.quantity,
            f"cantidad de '{product.name}'",
            allow_zero=False,
        )
        weight_kg = _preview_decimal(
            output.net_weight_kg,
            f"peso neto de '{product.name}'",
            allow_zero=False,
        )

        if output.unit_id != product.base_unit_id:
            raise ProductionPreviewValidationError(
                f"'{product.name}' debe usar su unidad base en producción."
            )

        if output.output_kind not in ("MAIN", "BYPRODUCT", "REWORK"):
            raise ProductionPreviewValidationError(
                f"Tipo de salida inválido: {output.output_kind}."
            )

        if not output.batch_code or not output.batch_code.strip():
            raise ProductionPreviewValidationError(
                f"'{product.name}' necesita código de lote terminado."
            )

        output_weight_kg += weight_kg
        total_finished_units += quantity

        serialized_outputs.append(
            {
                "product_id": product.id,
                "product_name": product.name,
                "sku": product.sku,
                "batch_code": output.batch_code.strip(),
                "quantity": _serialize_decimal(_quantity(quantity)),
                "unit_id": output.unit_id,
                "net_weight_kg": _serialize_decimal(_quantity(weight_kg)),
                "output_kind": output.output_kind,
                "unit_sale_price": (
                    _serialize_decimal(_money(output.unit_sale_price))
                    if output.unit_sale_price is not None
                    else None
                ),
                "notes": output.notes,
            }
        )

    if output_weight_kg <= ZERO:
        raise ProductionPreviewValidationError(
            "El peso neto total de salidas debe ser mayor que cero."
        )

    serialized_wastes: list[dict[str, Any]] = []
    waste_quantity_base = ZERO

    for waste in request.wastes:
        if waste.waste_type not in WASTE_TYPES:
            raise ProductionPreviewValidationError(
                f"Tipo de merma inválido: {waste.waste_type}."
            )

        if waste.cost_treatment not in WASTE_COST_TREATMENTS:
            raise ProductionPreviewValidationError(
                f"Tratamiento de merma inválido: {waste.cost_treatment}."
            )

        quantity = _preview_decimal(
            waste.quantity,
            "cantidad de merma",
            allow_zero=False,
        )
        quantity_base = _preview_decimal(
            waste.quantity_base,
            "cantidad base de merma",
            allow_zero=False,
        )

        waste_quantity_base += quantity_base

        serialized_wastes.append(
            {
                "waste_type": waste.waste_type,
                "quantity": _serialize_decimal(_quantity(quantity)),
                "unit_id": waste.unit_id,
                "quantity_base": _serialize_decimal(
                    _quantity(quantity_base)
                ),
                "is_expected": waste.is_expected,
                "is_recoverable": waste.is_recoverable,
                "recovered_product_id": waste.recovered_product_id,
                "cost_treatment": waste.cost_treatment,
                "notes": waste.notes,
            }
        )

    if output_weight_kg + waste_quantity_base > source_quantity_base:
        raise ProductionPreviewValidationError(
            "La salida terminada y la merma superan el insumo procesado."
        )

    unexplained_difference_kg = _quantity(
        source_quantity_base
        - output_weight_kg
        - waste_quantity_base
    )

    if request.mode == "REAL" and unexplained_difference_kg > Decimal("0.0001"):
        raise ProductionPreviewValidationError(
            "En producción REAL debes clasificar toda la diferencia como "
            "merma, subproducto o salida recuperable."
        )

    serialized_inputs: list[dict[str, Any]] = []
    physical_input_cost = ZERO

    for material in request.inputs:
        product = _preview_required_record(
            session,
            Product,
            material.product_id,
            "un insumo físico",
        )
        location = _preview_required_record(
            session,
            InventoryLocation,
            material.location_id,
            "la ubicación de un insumo",
        )

        quantity = _preview_decimal(
            material.quantity,
            f"cantidad de '{product.name}'",
            allow_zero=False,
        )
        quantity_base = _preview_decimal(
            material.quantity_base,
            f"cantidad base de '{product.name}'",
            allow_zero=False,
        )

        if material.unit_id != product.base_unit_id:
            raise ProductionPreviewValidationError(
                f"El insumo '{product.name}' debe usar unidad base."
            )

        if request.mode == "SIMULATION":
            unit_cost = _preview_decimal(
                material.estimated_unit_cost,
                f"costo estimado de '{product.name}'",
                allow_zero=True,
            )
        else:
            available = get_available_quantity(
                session,
                product.id,
                location.id,
                material.batch_id,
            )

            if quantity_base > available:
                raise ProductionPreviewValidationError(
                    f"No hay suficiente inventario de '{product.name}'."
                )

            unit_cost_value = session.scalar(
                select(InventoryBalance.average_unit_cost).where(
                    InventoryBalance.product_id == product.id,
                    InventoryBalance.location_id == location.id,
                    InventoryBalance.batch_id == material.batch_id,
                )
            )

            unit_cost = Decimal(str(unit_cost_value or ZERO))

        line_cost = _money(quantity_base * unit_cost)
        physical_input_cost += line_cost

        serialized_inputs.append(
            {
                "product_id": product.id,
                "product_name": product.name,
                "location_id": location.id,
                "location_name": location.name,
                "batch_id": material.batch_id,
                "quantity": _serialize_decimal(_quantity(quantity)),
                "quantity_base": _serialize_decimal(
                    _quantity(quantity_base)
                ),
                "unit_id": material.unit_id,
                "unit_cost": _serialize_decimal(unit_cost),
                "line_cost": _serialize_decimal(line_cost),
                "notes": material.notes,
            }
        )

    serialized_manual_costs: list[dict[str, Any]] = []
    manual_process_cost = ZERO
    manual_overhead_cost = ZERO

    for cost in request.manual_costs:
        if cost.cost_type not in PRODUCTION_COST_TYPES:
            raise ProductionPreviewValidationError(
                f"Tipo de costo inválido: {cost.cost_type}."
            )

        if not cost.description or not cost.description.strip():
            raise ProductionPreviewValidationError(
                "Todo costo manual necesita una descripción."
            )

        amount = _money(
            _preview_decimal(
                cost.amount,
                cost.description,
                allow_zero=False,
            )
        )

        if cost.supplier_party_id is not None:
            _preview_required_record(
                session,
                Party,
                cost.supplier_party_id,
                "el proveedor del costo",
            )

        is_executor_cost = (
            cost.cost_type == "OTHER"
            and request.executor_party_id is not None
            and cost.supplier_party_id == request.executor_party_id
        )

        if is_executor_cost:
            manual_process_cost += amount
        else:
            manual_overhead_cost += amount

        serialized_manual_costs.append(
            {
                "cost_type": cost.cost_type,
                "description": cost.description.strip(),
                "amount": _serialize_decimal(amount),
                "supplier_party_id": cost.supplier_party_id,
                "supplier_document_number": cost.supplier_document_number,
                "occurred_on": (
                    cost.occurred_on.isoformat()
                    if cost.occurred_on
                    else None
                ),
                "notes": cost.notes,
            }
        )

    total_input_cost = _money(source_input_cost + physical_input_cost)
    total_process_cost = _money(manual_process_cost)
    total_overhead_cost = _money(manual_overhead_cost)
    total_cost = _money(
        total_input_cost
        + total_process_cost
        + total_overhead_cost
    )

    for output in serialized_outputs:
        weight_kg = Decimal(output["net_weight_kg"])
        allocation_pct = _safe_ratio(weight_kg, output_weight_kg)
        allocated_cost = _money(total_cost * allocation_pct)
        quantity = Decimal(output["quantity"])

        output["cost_allocation_pct"] = _serialize_decimal(
            allocation_pct.quantize(
                PERCENT_QUANTUM,
                rounding=ROUND_HALF_UP,
            )
        )
        output["allocated_cost"] = _serialize_decimal(allocated_cost)
        output["unit_cost"] = _serialize_decimal(
            allocated_cost / quantity
        )

        if output["unit_sale_price"] is not None:
            unit_sale_price = Decimal(output["unit_sale_price"])
            potential_revenue = _money(quantity * unit_sale_price)

            output["potential_revenue"] = _serialize_decimal(
                potential_revenue
            )
            output["potential_margin"] = _serialize_decimal(
                _money(potential_revenue - allocated_cost)
            )
        else:
            output["potential_revenue"] = None
            output["potential_margin"] = None

    yield_pct = _safe_ratio(output_weight_kg, source_quantity_base)

    return {
        "valid": True,
        "mode": request.mode,
        "historical_reconstruction": request.historical_reconstruction,
        "order_number": request.order_number.strip(),
        "source": {
            "product_id": source_product.id if source_product else None,
            "product_name": source_product.name if source_product else None,
            "batch_id": source_batch.id if source_batch else None,
            "batch_code": source_batch.batch_code if source_batch else None,
            "location_id": source_location.id if source_location else None,
            "location_name": source_location.name if source_location else None,
            "available_quantity_base": (
                _serialize_decimal(
                    _quantity(Decimal(source_balance.quantity_base))
                )
                if source_balance
                else None
            ),
            "processed_quantity_base": _serialize_decimal(
                _quantity(source_quantity_base)
            ),
            "source_unit_cost": _serialize_decimal(source_unit_cost),
            "source_input_cost": _serialize_decimal(source_input_cost),
        },
        "processor": {
            "process_id": process.id if process else None,
            "process_name": process.name if process else None,
            "executor_party_id": executor.id if executor else None,
            "executor_name": (
                executor.display_name if executor else None
            ),
            "processor_location_id": (
                processor_location.id if processor_location else None
            ),
            "processor_location_name": (
                processor_location.name if processor_location else None
            ),
            "destination_location_id": (
                destination_location.id if destination_location else None
            ),
            "destination_location_name": (
                destination_location.name if destination_location else None
            ),
        },
        "timing": {
            "started_at": (
                request.started_at.isoformat()
                if request.started_at
                else None
            ),
            "completed_at": (
                request.completed_at.isoformat()
                if request.completed_at
                else None
            ),
            "received_at": (
                request.received_at.isoformat()
                if request.received_at
                else None
            ),
        },
        "summary": {
            "source_quantity_base": _serialize_decimal(
                _quantity(source_quantity_base)
            ),
            "output_weight_kg": _serialize_decimal(
                _quantity(output_weight_kg)
            ),
            "output_quantity_count": _serialize_decimal(
                _quantity(total_finished_units)
            ),
            "waste_quantity_base": _serialize_decimal(
                _quantity(waste_quantity_base)
            ),
            "unexplained_difference_base": _serialize_decimal(
                unexplained_difference_kg
            ),
            "yield_pct": _serialize_decimal(
                yield_pct.quantize(
                    PERCENT_QUANTUM,
                    rounding=ROUND_HALF_UP,
                )
            ),
            "yield_display_pct": _serialize_decimal(
                (yield_pct * HUNDRED).quantize(
                    Decimal("0.01"),
                    rounding=ROUND_HALF_UP,
                )
            ),
            "total_input_cost": _serialize_decimal(total_input_cost),
            "total_process_cost": _serialize_decimal(total_process_cost),
            "total_overhead_cost": _serialize_decimal(
                total_overhead_cost
            ),
            "total_cost": _serialize_decimal(total_cost),
            "cost_per_finished_kg": _serialize_decimal(
                _money(total_cost / output_weight_kg)
            ),
            "cost_per_finished_unit": _serialize_decimal(
                _money(total_cost / total_finished_units)
            ),
        },
        "outputs": serialized_outputs,
        "wastes": serialized_wastes,
        "inputs": serialized_inputs,
        "manual_costs": serialized_manual_costs,
        "warnings": _preview_warnings(
            request,
            unexplained_difference_kg=unexplained_difference_kg,
        ),
    }

class ProductionConfirmationError(ValueError):
    """Error al confirmar una producción y generar movimientos reales."""


def _confirmation_datetime(
    request: ProductionPreviewRequest,
) -> datetime:
    """
    Fecha efectiva de movimientos:
    recepción > terminación > inicio > ahora UTC.
    """

    if request.received_at is not None:
        return request.received_at

    if request.completed_at is not None:
        return request.completed_at

    if request.started_at is not None:
        return request.started_at

    return datetime.now(timezone.utc)


def _confirmation_date(
    request: ProductionPreviewRequest,
) -> date:
    return _confirmation_datetime(request).date()


def _validate_confirmation_request(
    request: ProductionPreviewRequest,
    preview: dict[str, Any],
) -> None:
    if request.mode not in ("REAL", "HISTORICAL"):
        raise ProductionConfirmationError(
            "Solo se pueden confirmar producciones REAL o HISTORICAL. "
            "Las simulaciones no crean inventario."
        )

    difference = Decimal(
        preview["summary"]["unexplained_difference_base"]
    )

    if abs(difference) > Decimal("0.0001"):
        raise ProductionConfirmationError(
            "No se puede confirmar la producción porque existe una "
            "diferencia de masa sin clasificar."
        )

    if not request.destination_location_id:
        raise ProductionConfirmationError(
            "Debes seleccionar una ubicación destino para el producto terminado."
        )

    if not request.source_product_id:
        raise ProductionConfirmationError(
            "Debes seleccionar el producto origen."
        )

    if not request.source_batch_id:
        raise ProductionConfirmationError(
            "Debes seleccionar el lote origen."
        )

    if not request.source_location_id:
        raise ProductionConfirmationError(
            "Debes seleccionar la ubicación origen."
        )

    if request.mode == "REAL":
        missing = []

        if request.process_id is None:
            missing.append("proceso")

        if request.executor_party_id is None:
            missing.append("ejecutor")

        if request.processor_location_id is None:
            missing.append("ubicación del procesador")

        if missing:
            raise ProductionConfirmationError(
                "La producción REAL requiere: " + ", ".join(missing) + "."
            )


def _allocate_confirmation_costs(
    preview: dict[str, Any],
) -> list[dict[str, Any]]:
    """
    Convierte los outputs serializados del preview a estructuras Decimal y
    absorbe cualquier residuo de redondeo COP en la última salida.
    """

    outputs = preview["outputs"]

    if not outputs:
        raise ProductionConfirmationError(
            "El preview no contiene salidas para confirmar."
        )

    total_cost = Decimal(preview["summary"]["total_cost"])
    allocated_total = Decimal("0")
    allocated: list[dict[str, Any]] = []

    for index, output in enumerate(outputs):
        quantity = Decimal(output["quantity"])
        weight_kg = Decimal(output["net_weight_kg"])

        if index == len(outputs) - 1:
            allocated_cost = total_cost - allocated_total
        else:
            allocated_cost = Decimal(output["allocated_cost"])
            allocated_total += allocated_cost

        if quantity <= ZERO:
            raise ProductionConfirmationError(
                "Una salida confirmada debe tener cantidad positiva."
            )

        allocated.append(
            {
                "product_id": int(output["product_id"]),
                "batch_code": str(output["batch_code"]),
                "quantity": _quantity(quantity),
                "unit_id": int(output["unit_id"]),
                "net_weight_kg": _quantity(weight_kg),
                "output_kind": str(output["output_kind"]),
                "cost_allocation_pct": Decimal(
                    output["cost_allocation_pct"]
                ),
                "allocated_cost": _money(allocated_cost),
                "unit_cost": _money(allocated_cost / quantity),
                "notes": output.get("notes"),
            }
        )

    return allocated


def confirm_production(
    session: Session,
    request: ProductionPreviewRequest,
    *,
    created_by_id: int | None = None,
) -> dict[str, Any]:
    """
    Confirma una producción genérica usando el mismo contrato del preview.

    Esta función:
    - Recalcula y revalida el preview.
    - Crea orden, ejecución, inputs, outputs, merma y costos.
    - Crea lotes terminados y linaje.
    - Genera movimientos OUT_PRODUCTION e IN_PRODUCTION.
    - Actualiza balances exclusivamente mediante inventory_service.

    No hace commit ni rollback. La ruta HTTP controla el límite transaccional.
    """

    try:
        preview = preview_production(session, request)
    except ProductionPreviewValidationError as exc:
        raise ProductionConfirmationError(str(exc)) from exc

    _validate_confirmation_request(request, preview)

    duplicate_order = session.scalar(
        select(ProductionOrder).where(
            ProductionOrder.order_number == request.order_number.strip()
        )
    )

    if duplicate_order is not None:
        raise ProductionConfirmationError(
            f"La orden '{request.order_number.strip()}' ya existe "
            f"(ID {duplicate_order.id})."
        )

    for output in preview["outputs"]:
        existing_batch = session.scalar(
            select(Batch).where(
                Batch.batch_code == output["batch_code"]
            )
        )

        if existing_batch is not None:
            raise ProductionConfirmationError(
                f"El código de lote terminado '{output['batch_code']}' "
                "ya existe."
            )

    source_product = session.get(Product, request.source_product_id)
    source_batch = session.get(Batch, request.source_batch_id)
    source_location = session.get(
        InventoryLocation,
        request.source_location_id,
    )
    destination_location = session.get(
        InventoryLocation,
        request.destination_location_id,
    )

    if (
        source_product is None
        or source_batch is None
        or source_location is None
        or destination_location is None
    ):
        raise ProductionConfirmationError(
            "No fue posible recuperar los datos de origen o destino."
        )

    occurred_at = _confirmation_datetime(request)
    produced_on = _confirmation_date(request)

    source_quantity = _preview_decimal(
        request.source_quantity,
        "cantidad del insumo origen",
        allow_zero=False,
    )
    source_quantity_base = _preview_decimal(
        request.source_quantity_base,
        "cantidad base del insumo origen",
        allow_zero=False,
    )

    allocated_outputs = _allocate_confirmation_costs(preview)

    order = ProductionOrder(
        order_number=request.order_number.strip(),
        status="COMPLETED",
        target_product_id=(
            allocated_outputs[0]["product_id"]
            if len(allocated_outputs) == 1
            else None
        ),
        planned_quantity=sum(
            (output["quantity"] for output in allocated_outputs),
            ZERO,
        ),
        unit_id=(
            allocated_outputs[0]["unit_id"]
            if len(allocated_outputs) == 1
            else None
        ),
        planned_start_date=produced_on,
        started_at=request.started_at,
        completed_at=request.completed_at or occurred_at,
        total_input_cost=Decimal(preview["summary"]["total_input_cost"]),
        total_process_cost=Decimal(
            preview["summary"]["total_process_cost"]
        ),
        total_overhead_cost=Decimal(
            preview["summary"]["total_overhead_cost"]
        ),
        total_cost=Decimal(preview["summary"]["total_cost"]),
        output_quantity_base=Decimal(
            preview["summary"]["output_weight_kg"]
        ),
        waste_quantity_base=Decimal(
            preview["summary"]["waste_quantity_base"]
        ),
        yield_pct=Decimal(preview["summary"]["yield_pct"]),
        unit_cost=Decimal(
            preview["summary"]["cost_per_finished_unit"]
        ),
        currency=request.currency or "COP",
        notes=request.notes,
        created_by_id=created_by_id,
        updated_by_id=created_by_id,
    )
    session.add(order)
    session.flush()

    execution = None

    if request.process_id is not None:
        execution = ProcessExecution(
            production_order_id=order.id,
            process_id=request.process_id,
            sequence_no=1,
            executor_type=(
                "EXTERNAL"
                if request.executor_party_id is not None
                else "INTERNAL"
            ),
            executor_party_id=request.executor_party_id,
            location_id=request.processor_location_id,
            status=(
                "RECEIVED"
                if request.received_at is not None
                else "DONE"
            ),
            sent_at=request.started_at,
            started_at=request.started_at,
            finished_at=request.completed_at or occurred_at,
            received_at=request.received_at,
            input_quantity_base=source_quantity_base,
            output_quantity_base=Decimal(
                preview["summary"]["output_weight_kg"]
            ),
            waste_quantity_base=Decimal(
                preview["summary"]["waste_quantity_base"]
            ),
            yield_pct=Decimal(preview["summary"]["yield_pct"]),
            computed_cost=Decimal(
                preview["summary"]["total_process_cost"]
            ),
            actual_cost=Decimal(
                preview["summary"]["total_process_cost"]
            ),
            currency=request.currency or "COP",
            notes="Ejecución creada al confirmar producción.",
            created_by_id=created_by_id,
            updated_by_id=created_by_id,
        )
        session.add(execution)
        session.flush()

    source_input = ProductionInput(
        production_order_id=order.id,
        process_execution_id=execution.id if execution else None,
        product_id=source_product.id,
        batch_id=source_batch.id,
        quantity=source_quantity,
        unit_id=request.source_unit_id or source_product.base_unit_id,
        quantity_base=source_quantity_base,
        unit_cost=Decimal(preview["source"]["source_unit_cost"]),
        total_cost=Decimal(preview["source"]["source_input_cost"]),
        currency=request.currency or "COP",
        consumed_at=occurred_at,
        notes="Insumo origen de la producción.",
    )
    session.add(source_input)
    session.flush()

    source_movement = create_production_input_movement(
        session,
        product_id=source_product.id,
        location_id=source_location.id,
        quantity=source_quantity,
        unit_id=request.source_unit_id or source_product.base_unit_id,
        quantity_base=source_quantity_base,
        batch_id=source_batch.id,
        reference_id=source_input.id,
        occurred_at=occurred_at,
        created_by_id=created_by_id,
        notes="Consumo de lote origen en producción.",
    )
    source_input.movement_id = source_movement.id

    input_records: list[ProductionInput] = [source_input]

    for material in preview["inputs"]:
        production_input = ProductionInput(
            production_order_id=order.id,
            process_execution_id=None,
            product_id=int(material["product_id"]),
            batch_id=material["batch_id"],
            quantity=Decimal(material["quantity"]),
            unit_id=int(material["unit_id"]),
            quantity_base=Decimal(material["quantity_base"]),
            unit_cost=Decimal(material["unit_cost"]),
            total_cost=Decimal(material["line_cost"]),
            currency=request.currency or "COP",
            consumed_at=occurred_at,
            notes=material.get("notes"),
        )
        session.add(production_input)
        session.flush()

        movement = create_production_input_movement(
            session,
            product_id=production_input.product_id,
            location_id=int(material["location_id"]),
            quantity=Decimal(material["quantity"]),
            unit_id=production_input.unit_id,
            quantity_base=production_input.quantity_base,
            batch_id=production_input.batch_id,
            reference_id=production_input.id,
            occurred_at=occurred_at,
            created_by_id=created_by_id,
            notes=production_input.notes,
        )
        production_input.movement_id = movement.id
        input_records.append(production_input)

    waste_records: list[ProductionWaste] = []

    for waste in preview["wastes"]:
        quantity = Decimal(waste["quantity"])
        quantity_base = Decimal(waste["quantity_base"])

        waste_record = ProductionWaste(
            production_order_id=order.id,
            process_execution_id=execution.id if execution else None,
            product_id=source_product.id,
            batch_id=source_batch.id,
            quantity=quantity,
            unit_id=int(waste["unit_id"]),
            quantity_base=quantity_base,
            waste_type=waste["waste_type"],
            is_expected=bool(waste["is_expected"]),
            is_recoverable=bool(waste["is_recoverable"]),
            recovered_product_id=waste["recovered_product_id"],
            cost_treatment=waste["cost_treatment"],
            cost_amount=Decimal("0"),
            occurred_at=occurred_at,
            notes=waste.get("notes"),
        )
        session.add(waste_record)
        session.flush()
        waste_records.append(waste_record)

    cost_records: list[ProductionCost] = []

    for manual_cost in preview["manual_costs"]:
        cost_record = ProductionCost(
            production_order_id=order.id,
            process_execution_id=(
                execution.id
                if (
                    manual_cost["cost_type"] == "OTHER"
                    and request.executor_party_id is not None
                    and manual_cost["supplier_party_id"]
                    == request.executor_party_id
                )
                else None
            ),
            cost_type=manual_cost["cost_type"],
            description=manual_cost["description"],
            amount=Decimal(manual_cost["amount"]),
            currency=request.currency or "COP",
            supplier_party_id=manual_cost["supplier_party_id"],
            supplier_document_number=manual_cost[
                "supplier_document_number"
            ],
            occurred_on=produced_on,
            notes=manual_cost.get("notes"),
        )
        session.add(cost_record)
        cost_records.append(cost_record)

    session.flush()

    output_records: list[dict[str, Any]] = []

    for output_data in allocated_outputs:
        output_product = session.get(
            Product,
            output_data["product_id"],
        )

        if output_product is None:
            raise ProductionConfirmationError(
                "No existe uno de los productos terminados."
            )

        finished_batch = Batch(
            batch_code=output_data["batch_code"],
            product_id=output_product.id,
            batch_type="PRODUCED",
            origin_party_id=source_batch.origin_party_id,
            origin_address_id=source_batch.origin_address_id,
            farm_name=source_batch.farm_name,
            municipality_name=source_batch.municipality_name,
            harvest_year=source_batch.harvest_year,
            harvest_period=source_batch.harvest_period,
            production_order_id=order.id,
            initial_quantity=output_data["quantity"],
            unit_id=output_data["unit_id"],
            unit_cost=output_data["unit_cost"],
            currency=request.currency or "COP",
            received_date=produced_on,
            production_date=produced_on,
            status="ACTIVE",
            quality_notes=output_data.get("notes"),
            created_by_id=created_by_id,
            updated_by_id=created_by_id,
        )
        session.add(finished_batch)
        session.flush()

        output_record = ProductionOutput(
            production_order_id=order.id,
            process_execution_id=execution.id if execution else None,
            product_id=output_product.id,
            batch_id=finished_batch.id,
            quantity=output_data["quantity"],
            unit_id=output_data["unit_id"],
            quantity_base=output_data["quantity"],
            output_kind=output_data["output_kind"],
            cost_allocation_pct=output_data[
                "cost_allocation_pct"
            ],
            allocated_cost=output_data["allocated_cost"],
            unit_cost=output_data["unit_cost"],
            currency=request.currency or "COP",
            location_id=destination_location.id,
            produced_at=occurred_at,
            notes=output_data.get("notes"),
        )
        session.add(output_record)
        session.flush()

        output_movement = create_production_output_movement(
            session,
            product_id=output_product.id,
            location_id=destination_location.id,
            quantity=output_data["quantity"],
            unit_id=output_data["unit_id"],
            quantity_base=output_data["quantity"],
            batch_id=finished_batch.id,
            unit_cost=output_data["unit_cost"],
            total_cost=output_data["allocated_cost"],
            reference_id=output_record.id,
            occurred_at=occurred_at,
            created_by_id=created_by_id,
            notes=output_data.get("notes"),
        )
        output_record.movement_id = output_movement.id

        contribution_pct = Decimal(
            output_data["cost_allocation_pct"]
        )

        lineage = BatchLineage(
            child_batch_id=finished_batch.id,
            parent_batch_id=source_batch.id,
            quantity_consumed=(
                source_quantity_base * contribution_pct
            ).quantize(
                QUANTITY_QUANTUM,
                rounding=ROUND_HALF_UP,
            ),
            unit_id=source_product.base_unit_id,
            contribution_pct=contribution_pct,
            production_order_id=order.id,
        )
        session.add(lineage)

        output_records.append(
            {
                "production_output": output_record,
                "batch": finished_batch,
                "inventory_movement": output_movement,
            }
        )

    session.flush()

    order.status = "COMPLETED"
    order.updated_by_id = created_by_id

    return {
        "order_id": order.id,
        "order_number": order.order_number,
        "mode": request.mode,
        "total_cost": preview["summary"]["total_cost"],
        "destination_location_id": destination_location.id,
        "destination_location_name": destination_location.name,
        "source_movement_id": source_movement.id,
        "input_count": len(input_records),
        "waste_count": len(waste_records),
        "cost_count": len(cost_records),
        "outputs": [
            {
                "production_output_id": item["production_output"].id,
                "product_id": item["production_output"].product_id,
                "batch_id": item["batch"].id,
                "batch_code": item["batch"].batch_code,
                "quantity": _serialize_decimal(
                    Decimal(item["production_output"].quantity)
                ),
                "unit_cost": _serialize_decimal(
                    Decimal(item["production_output"].unit_cost)
                ),
                "allocated_cost": _serialize_decimal(
                    Decimal(item["production_output"].allocated_cost)
                ),
                "location_id": destination_location.id,
                "location_name": destination_location.name,
                "movement_id": item["inventory_movement"].id,
            }
            for item in output_records
        ],
    }


__all__ = [
    "DEFAULTS",
    "HistoricalLotDefaults",
    "HistoricalPreviewValidationError",
    "ProductionInputPreviewRequest",
    "ProductionManualCostPreviewRequest",
    "ProductionOutputPreviewRequest",
    "ProductionPreviewRequest",
    "ProductionPreviewValidationError",
    "ProductionWastePreviewRequest",
    "confirm_production",
    "historical_microlot_preview",
    "preview_production",
]