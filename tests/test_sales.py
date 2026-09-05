from __future__ import annotations

from decimal import Decimal

import pytest

from app.services.inventory_service import get_available_quantity, receive_purchase
from app.services.sale_services import (
	SaleError,
	add_sale_item,
	allocate_sale_item_batches,
	cancel_sale,
	confirm_sale,
	create_sale,
)


def batch_code(purchase, item):
	return f"L-{purchase.purchase_number}-{item.line_no}"


def prepare_inventory(session, confirmed_purchase):
	return receive_purchase(
		session,
		confirmed_purchase,
		batch_code_factory=batch_code,
	)[0]


def test_create_sale_requires_customer_role(session, supplier):
	with pytest.raises(SaleError):
		create_sale(
			session,
			sale_number="V-TEST-001",
			party_id=supplier.id,
			channel="RETAIL",
		)


def test_confirm_sale_consumes_inventory_and_stores_margin(
	session, customer, confirmed_purchase, coffee_product, warehouse, lb
):
	batch = prepare_inventory(session, confirmed_purchase)
	sale = create_sale(
		session,
		sale_number="V-TEST-001",
		party_id=customer.id,
		channel="RETAIL",
	)
	item = add_sale_item(
		session,
		sale,
		product_id=coffee_product.id,
		quantity=Decimal("30"),
		unit_id=lb.id,
		manual_unit_price=Decimal("6000"),
	)
	allocate_sale_item_batches(
		session,
		item,
		[{
			"batch_id": batch.id,
			"location_id": warehouse.id,
			"quantity_base": Decimal("30"),
		}],
	)
	confirm_sale(session, sale)

	assert sale.status == "CONFIRMED"
	assert sale.total == Decimal("180000.00")
	assert sale.cost_total == Decimal("90000.00")
	assert sale.margin_amount == Decimal("90000.00")
	assert item.price_source == "MANUAL"
	assert item.unit_cost == Decimal("3000.0000")
	assert get_available_quantity(
		session, coffee_product.id, warehouse.id, batch.id
	) == Decimal("70")


def test_cancel_confirmed_sale_restores_inventory(
	session, customer, confirmed_purchase, coffee_product, warehouse, lb
):
	batch = prepare_inventory(session, confirmed_purchase)
	sale = create_sale(
		session,
		sale_number="V-TEST-002",
		party_id=customer.id,
		channel="RETAIL",
	)
	item = add_sale_item(
		session,
		sale,
		product_id=coffee_product.id,
		quantity=Decimal("30"),
		unit_id=lb.id,
		manual_unit_price=Decimal("6000"),
	)
	allocate_sale_item_batches(
		session,
		item,
		[{"batch_id": batch.id, "location_id": warehouse.id, "quantity_base": Decimal("30")}],
	)
	confirm_sale(session, sale)
	cancel_sale(session, sale, reason="Prueba de cancelacion")

	assert sale.status == "CANCELLED"
	assert get_available_quantity(
		session, coffee_product.id, warehouse.id, batch.id
	) == Decimal("100")


def test_sales_api_can_create_sale_and_line(app, customer, coffee_product, lb):
	with app.test_client() as client:
		response = client.post(
			"/api/v1/sales",
			json={
				"sale_number": "V-API-001",
				"party_id": customer.id,
				"channel": "RETAIL",
			},
		)
		assert response.status_code == 201, response.get_data(as_text=True)
		payload = response.get_json()
		assert payload["sale_number"] == "V-API-001"
		assert payload["status"] == "DRAFT"

		sale_id = payload["id"]
		line_response = client.post(
			f"/api/v1/sales/{sale_id}/items",
			json={
				"product_id": coffee_product.id,
				"quantity": "30",
				"unit_id": lb.id,
				"manual_unit_price": "6000",
			},
		)
		assert line_response.status_code == 201, line_response.get_data(as_text=True)
		line_payload = line_response.get_json()
		assert line_payload["sale_id"] == sale_id
		assert line_payload["total"] == "180000.00"
