from __future__ import annotations

from decimal import Decimal

import pytest

from app.services.inventory_service import (
	InventoryError,
	create_outbound_movement,
	get_available_quantity,
	receive_purchase,
	reverse_movement,
)


def batch_code(purchase, item):
	return f"L-{purchase.purchase_number}-{item.line_no}"


def test_receive_purchase_creates_batch_and_balance(
	session, confirmed_purchase, coffee_product, warehouse
):
	batches = receive_purchase(
		session,
		confirmed_purchase,
		batch_code_factory=batch_code,
	)
	session.commit()

	assert confirmed_purchase.status == "RECEIVED"
	assert len(batches) == 1
	assert get_available_quantity(
		session, coffee_product.id, warehouse.id, batches[0].id
	) == Decimal("100")


def test_outbound_reduces_balance_and_rejects_excess(
	session, confirmed_purchase, coffee_product, warehouse, lb
):
	batches = receive_purchase(
		session,
		confirmed_purchase,
		batch_code_factory=batch_code,
	)
	session.flush()

	create_outbound_movement(
		session,
		product_id=coffee_product.id,
		location_id=warehouse.id,
		batch_id=batches[0].id,
		quantity=Decimal("30"),
		unit_id=lb.id,
		quantity_base=Decimal("30"),
	)
	assert get_available_quantity(
		session, coffee_product.id, warehouse.id, batches[0].id
	) == Decimal("70")

	with pytest.raises(InventoryError):
		create_outbound_movement(
			session,
			product_id=coffee_product.id,
			location_id=warehouse.id,
			batch_id=batches[0].id,
			quantity=Decimal("71"),
			unit_id=lb.id,
			quantity_base=Decimal("71"),
		)


def test_reverse_movement_restores_balance(
	session, confirmed_purchase, coffee_product, warehouse, lb
):
	batches = receive_purchase(
		session,
		confirmed_purchase,
		batch_code_factory=batch_code,
	)
	movement = create_outbound_movement(
		session,
		product_id=coffee_product.id,
		location_id=warehouse.id,
		batch_id=batches[0].id,
		quantity=Decimal("30"),
		unit_id=lb.id,
		quantity_base=Decimal("30"),
	)
	reversal = reverse_movement(session, movement.id)

	assert reversal.reverses_movement_id == movement.id
	assert get_available_quantity(
		session, coffee_product.id, warehouse.id, batches[0].id
	) == Decimal("100")
