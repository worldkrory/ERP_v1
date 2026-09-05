"""Servicios transaccionales del libro de inventario."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.models.batch import Batch
from app.models.inventory import InventoryBalance, InventoryLocation, InventoryMovement
from app.models.product import Product
from app.models.purchase import Purchase
from app.services.costing import CostingError, resolve_outbound_cost
from app.services.units import UnitConversionError, convert_quantity


class InventoryError(ValueError):
	"""Error de dominio del inventario."""


def get_available_quantity(
	session: Session,
	product_id: int,
	location_id: int,
	batch_id: int | None = None,
) -> Decimal:
	filters = [
		InventoryBalance.product_id == product_id,
		InventoryBalance.location_id == location_id,
	]
	if batch_id is None:
		filters.append(InventoryBalance.batch_id.is_(None))
	else:
		filters.append(InventoryBalance.batch_id == batch_id)
	value = session.scalar(
		select(func.coalesce(func.sum(InventoryBalance.quantity_base), 0)).where(*filters)
	)
	return Decimal(str(value or 0))


def _update_balance(
	session: Session,
	movement: InventoryMovement,
) -> InventoryBalance:
	balance = session.scalar(
		select(InventoryBalance)
		.where(
			InventoryBalance.product_id == movement.product_id,
			InventoryBalance.batch_id == movement.batch_id,
			InventoryBalance.location_id == movement.location_id,
		)
		.with_for_update()
	)
	if balance is None:
		balance = InventoryBalance(
			product_id=movement.product_id,
			batch_id=movement.batch_id,
			location_id=movement.location_id,
			quantity_base=Decimal("0"),
			average_unit_cost=Decimal("0"),
			total_value=Decimal("0"),
		)
		session.add(balance)
		session.flush()

	signed_quantity = Decimal(movement.quantity_base) * movement.direction
	movement_cost = Decimal(movement.total_cost or 0)
	new_quantity = Decimal(balance.quantity_base) + signed_quantity
	new_value = Decimal(balance.total_value) + (
		movement_cost if movement.direction == 1 else -movement_cost
	)
	if new_quantity < 0:
		raise InventoryError("El saldo de inventario no puede quedar negativo.")
	balance.quantity_base = new_quantity
	balance.total_value = max(new_value, Decimal("0"))
	balance.average_unit_cost = (
		balance.total_value / new_quantity if new_quantity else Decimal("0")
	)
	balance.last_movement_id = movement.id
	balance.last_movement_at = movement.occurred_at
	return balance


def _create_movement(
	session: Session,
	*,
	movement_type: str,
	product_id: int,
	location_id: int,
	quantity: Decimal,
	unit_id: int,
	quantity_base: Decimal,
	batch_id: int | None = None,
	unit_cost: Decimal | None = None,
	total_cost: Decimal | None = None,
	reference_type: str | None = None,
	reference_id: int | None = None,
	occurred_at: datetime | None = None,
	created_by_id: int | None = None,
	notes: str | None = None,
) -> InventoryMovement:
	if quantity <= 0 or quantity_base <= 0:
		raise InventoryError("Las cantidades del movimiento deben ser positivas.")
	product = session.get(Product, product_id)
	location = session.get(InventoryLocation, location_id)
	if product is None or not product.is_active:
		raise InventoryError("El producto no existe o esta inactivo.")
	if location is None or not location.is_active:
		raise InventoryError("La ubicacion no existe o esta inactiva.")
	if product.tracks_batches and batch_id is None:
		raise InventoryError("Este producto exige un lote.")
	if batch_id is not None:
		batch = session.get(Batch, batch_id)
		if batch is None or batch.product_id != product_id:
			raise InventoryError("El lote no pertenece al producto.")

	direction = 1 if movement_type.startswith("IN_") else -1
	movement = InventoryMovement(
		movement_type=movement_type,
		direction=direction,
		product_id=product_id,
		batch_id=batch_id,
		location_id=location_id,
		quantity=quantity,
		unit_id=unit_id,
		quantity_base=quantity_base,
		unit_cost=unit_cost,
		total_cost=total_cost,
		occurred_at=occurred_at or datetime.now(timezone.utc),
		reference_type=reference_type,
		reference_id=reference_id,
		created_by_id=created_by_id,
		notes=notes,
	)
	if direction == -1 and not location.allows_negative_stock:
		if get_available_quantity(session, product_id, location_id, batch_id) < quantity_base:
			raise InventoryError("No hay inventario suficiente para la salida.")
	session.add(movement)
	session.flush()
	_update_balance(session, movement)
	if batch_id is not None:
		batch = session.get(Batch, batch_id)
		if get_available_quantity(session, product_id, location_id, batch_id) == 0:
			batch.status = "DEPLETED"
	return movement


def receive_purchase(
	session: Session,
	purchase: Purchase,
	*,
	batch_code_factory,
	created_by_id: int | None = None,
) -> list[Batch]:
	if purchase.status != "CONFIRMED":
		raise InventoryError("Solo se pueden recibir compras CONFIRMED.")
	if not purchase.items or purchase.destination_location_id is None:
		raise InventoryError("La compra necesita lineas y ubicacion destino.")
	if purchase.received_at is not None:
		raise InventoryError("La compra ya fue recibida.")

	batches: list[Batch] = []
	for item in purchase.items:
		product = item.product or session.get(Product, item.product_id)
		if product is None or not product.is_active:
			raise InventoryError("Una linea contiene un producto invalido.")
		quantity_base = Decimal(item.quantity_base)
		batch = None
		if product.tracks_batches:
			batch = Batch(
				batch_code=batch_code_factory(purchase, item),
				product_id=item.product_id,
				batch_type="PURCHASED",
				origin_party_id=purchase.party_id,
				purchase_item_id=item.id,
				initial_quantity=quantity_base,
				unit_id=product.base_unit_id,
				unit_cost=item.landed_unit_cost,
				currency=purchase.currency,
				received_date=purchase.purchase_date,
			)
			session.add(batch)
			session.flush()
			item.batch_id = batch.id
			batches.append(batch)
		movement = _create_movement(
			session,
			movement_type="IN_PURCHASE",
			product_id=item.product_id,
			location_id=purchase.destination_location_id,
			batch_id=batch.id if batch else None,
			quantity=quantity_base,
			unit_id=product.base_unit_id,
			quantity_base=quantity_base,
			unit_cost=item.landed_unit_cost,
			total_cost=item.landed_total,
			reference_type="PURCHASE_ITEM",
			reference_id=item.id,
			created_by_id=created_by_id,
		)
		item.batch_id = batch.id if batch else None
		movement.reference_id = item.id

	purchase.status = "RECEIVED"
	purchase.received_at = datetime.now(timezone.utc)
	session.flush()
	return batches


def create_inbound_movement(session: Session, **kwargs) -> InventoryMovement:
	return _create_movement(session, **kwargs)


def create_outbound_movement(
	session: Session,
	*,
	product_id: int,
	location_id: int,
	quantity: Decimal,
	unit_id: int,
	quantity_base: Decimal,
	batch_id: int | None = None,
	reference_type: str | None = None,
	reference_id: int | None = None,
	created_by_id: int | None = None,
	notes: str | None = None,
) -> InventoryMovement:
	try:
		resolution = resolve_outbound_cost(
			session, product_id, batch_id, location_id, quantity_base
		)
	except CostingError as exc:
		raise InventoryError(str(exc)) from exc
	return _create_movement(
		session,
		movement_type="OUT_SALE",
		product_id=product_id,
		location_id=location_id,
		batch_id=batch_id,
		quantity=quantity,
		unit_id=unit_id,
		quantity_base=quantity_base,
		unit_cost=resolution.unit_cost,
		total_cost=resolution.total_cost,
		reference_type=reference_type,
		reference_id=reference_id,
		created_by_id=created_by_id,
		notes=notes,
	)


def create_transfer(
	session: Session,
	*,
	product_id: int,
	batch_id: int | None,
	from_location_id: int,
	to_location_id: int,
	quantity: Decimal,
	unit_id: int,
	quantity_base: Decimal,
	created_by_id: int | None = None,
) -> tuple[InventoryMovement, InventoryMovement]:
	if from_location_id == to_location_id:
		raise InventoryError("El origen y destino del traslado deben ser distintos.")
	try:
		resolution = resolve_outbound_cost(
			session, product_id, batch_id, from_location_id, quantity_base
		)
	except CostingError as exc:
		raise InventoryError(str(exc)) from exc
	outbound = _create_movement(
		session,
		movement_type="OUT_TRANSFER",
		product_id=product_id,
		location_id=from_location_id,
		batch_id=batch_id,
		quantity=quantity,
		unit_id=unit_id,
		quantity_base=quantity_base,
		unit_cost=resolution.unit_cost,
		total_cost=resolution.total_cost,
		created_by_id=created_by_id,
	)
	inbound = _create_movement(
		session,
		movement_type="IN_TRANSFER",
		product_id=product_id,
		location_id=to_location_id,
		batch_id=batch_id,
		quantity=quantity,
		unit_id=unit_id,
		quantity_base=quantity_base,
		unit_cost=outbound.unit_cost,
		total_cost=outbound.total_cost,
		created_by_id=created_by_id,
	)
	outbound.counterpart_movement_id = inbound.id
	inbound.counterpart_movement_id = outbound.id
	return outbound, inbound


def reverse_movement(
	session: Session,
	movement_id: int,
	*,
	created_by_id: int | None = None,
	notes: str | None = None,
) -> InventoryMovement:
	original = session.get(InventoryMovement, movement_id)
	if original is None:
		raise InventoryError("El movimiento original no existe.")
	existing = session.scalar(
		select(InventoryMovement).where(
			InventoryMovement.reverses_movement_id == movement_id
		)
	)
	if existing is not None:
		raise InventoryError("El movimiento ya fue reversado.")
	reverse_types = {
		"OUT_SALE": "IN_SALE_RETURN",
		"OUT_PURCHASE_RETURN": "IN_PURCHASE",
	}
	reverse_type = reverse_types.get(
		original.movement_type,
		(
			original.movement_type.replace("IN_", "OUT_", 1)
			if original.direction == 1
			else original.movement_type.replace("OUT_", "IN_", 1)
		),
	)
	reversal = _create_movement(
		session,
		movement_type=reverse_type,
		product_id=original.product_id,
		location_id=original.location_id,
		batch_id=original.batch_id,
		quantity=original.quantity,
		unit_id=original.unit_id,
		quantity_base=original.quantity_base,
		unit_cost=original.unit_cost,
		total_cost=original.total_cost,
		reference_type="ADJUSTMENT",
		reference_id=original.id,
		created_by_id=created_by_id,
		notes=notes,
	)
	reversal.reverses_movement_id = original.id
	session.flush()
	return reversal


def rebuild_balances(session: Session) -> None:
	session.execute(delete(InventoryBalance))
	movements = session.scalars(
		select(InventoryMovement).order_by(
			InventoryMovement.occurred_at, InventoryMovement.id
		)
	).all()
	for movement in movements:
		_update_balance(session, movement)


__all__ = [
	"InventoryError",
	"create_inbound_movement",
	"create_outbound_movement",
	"create_transfer",
	"get_available_quantity",
	"receive_purchase",
	"rebuild_balances",
	"reverse_movement",
]