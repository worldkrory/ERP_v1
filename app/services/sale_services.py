"""Servicios de ventas y confirmacion de salidas de inventario."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.party import Party
from app.models.price import PartyPriceRule, PriceList, PriceListItem
from app.models.product import Product
from app.models.sale import Sale, SaleItem, SaleItemBatch
from app.models.tax import Tax
from app.services.costing import CostingError, resolve_outbound_cost
from app.services.inventory_service import InventoryError, create_outbound_movement
from app.services.units import UnitConversionError, convert_quantity


class SaleError(ValueError):
	"""Error de dominio de ventas."""


@dataclass(frozen=True)
class PriceResolution:
	unit_price: Decimal
	price_source: str
	price_list_item_id: int | None


def _money(value: Decimal) -> Decimal:
	return Decimal(value).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _current_rules(session: Session, party_id: int, day: date) -> list[PartyPriceRule]:
	rules = session.scalars(
		select(PartyPriceRule).where(
			PartyPriceRule.party_id == party_id,
			PartyPriceRule.is_active.is_(True),
		)
	).all()
	return [rule for rule in rules if rule.covers(day)]


def _resolve_price_list(
	session: Session,
	party: Party,
	channel: str,
	product: Product,
	quantity: Decimal,
	day: date,
) -> tuple[PriceList, str]:
	rules = sorted(_current_rules(session, party.id, day), key=lambda rule: rule.priority)
	assignment = next(
		(
			rule
			for rule in rules
			if rule.rule_type == "LIST_ASSIGNMENT"
			and (rule.product_id in (None, product.id))
			and (rule.category_id in (None, product.category_id))
			and quantity >= rule.min_quantity
		),
		None,
	)
	if assignment and assignment.price_list is not None:
		return assignment.price_list, "PARTY_RULE"
	if party.default_price_list is not None:
		return party.default_price_list, "PARTY_RULE"
	price_list = session.scalar(
		select(PriceList).where(
			PriceList.channel == channel,
			PriceList.is_default.is_(True),
			PriceList.is_active.is_(True),
		)
	)
	if price_list is None or not price_list.covers(day):
		raise SaleError("No existe una lista de precios vigente para el canal.")
	return price_list, "PRICE_LIST"


def resolve_sale_price(
	session: Session,
	party: Party,
	product: Product,
	unit_id: int,
	quantity: Decimal,
	channel: str,
	day: date,
) -> PriceResolution:
	rules = sorted(_current_rules(session, party.id, day), key=lambda rule: rule.priority)
	fixed = next(
		(
			rule
			for rule in rules
			if rule.rule_type == "FIXED_PRICE"
			and rule.product_id in (None, product.id)
			and rule.category_id in (None, product.category_id)
			and rule.unit_id == unit_id
			and rule.value is not None
			and quantity >= rule.min_quantity
		),
		None,
	)
	if fixed is not None:
		return PriceResolution(Decimal(fixed.value), "PARTY_RULE", None)

	price_list, source = _resolve_price_list(
		session, party, channel, product, quantity, day
	)
	if not price_list.is_active or not price_list.covers(day):
		raise SaleError("La lista de precios no esta vigente.")
	candidates = session.scalars(
		select(PriceListItem).where(
			PriceListItem.price_list_id == price_list.id,
			PriceListItem.product_id == product.id,
			PriceListItem.unit_id == unit_id,
			PriceListItem.is_active.is_(True),
		)
	).all()
	item = next(
		(candidate for candidate in candidates if candidate.covers(day)
		 and candidate.covers_quantity(quantity)),
		None,
	)
	if item is None:
		raise SaleError("No existe precio vigente para el producto y unidad.")

	price = Decimal(item.unit_price)
	for rule in rules:
		applies = (
			rule.rule_type in ("DISCOUNT_PCT", "DISCOUNT_AMOUNT")
			and rule.product_id in (None, product.id)
			and rule.category_id in (None, product.category_id)
			and (rule.unit_id in (None, unit_id))
			and quantity >= rule.min_quantity
			and rule.value is not None
		)
		if applies and rule.rule_type == "DISCOUNT_PCT":
			price *= Decimal("1") - Decimal(rule.value)
		elif applies:
			price -= Decimal(rule.value)
	if price < 0:
		raise SaleError("El precio no puede quedar negativo.")
	return PriceResolution(price, source, item.id)


def _recalculate_sale(sale: Sale) -> None:
	sale.subtotal = sum((Decimal(item.subtotal) for item in sale.items), Decimal("0"))
	sale.discount_total = sum(
		(Decimal(item.discount_amount) for item in sale.items), Decimal("0")
	)
	sale.tax_total = sum((Decimal(item.tax_amount) for item in sale.items), Decimal("0"))
	sale.total = _money(sum((Decimal(item.total) for item in sale.items), Decimal("0")))


def create_sale(
	session: Session,
	*,
	sale_number: str,
	party_id: int,
	channel: str,
	sale_date: date | None = None,
	salesperson_user_id: int | None = None,
	shipping_address_id: int | None = None,
) -> Sale:
	party = session.get(Party, party_id)
	if party is None or not party.is_active or not party.has_role("CUSTOMER"):
		raise SaleError("El tercero no existe, esta inactivo o no es cliente.")
	day = sale_date or date.today()
	sale = Sale(
		sale_number=sale_number,
		party_id=party_id,
		channel=channel,
		sale_date=day,
		payment_term_days=party.payment_term_days,
		due_date=day + timedelta(days=party.payment_term_days),
		salesperson_user_id=salesperson_user_id,
		shipping_address_id=shipping_address_id,
		currency="COP",
	)
	session.add(sale)
	session.flush()
	return sale


def add_sale_item(
	session: Session,
	sale: Sale,
	*,
	product_id: int,
	quantity: Decimal,
	unit_id: int,
	manual_unit_price: Decimal | None = None,
	discount_pct: Decimal = Decimal("0"),
) -> SaleItem:
	if not sale.is_editable or quantity <= 0:
		raise SaleError("La venta no esta editable o la cantidad es invalida.")
	product = session.get(Product, product_id)
	if product is None or not product.is_active or not product.is_sellable:
		raise SaleError("El producto no existe, esta inactivo o no es vendible.")
	party = sale.party or session.get(Party, sale.party_id)
	resolution = (
		PriceResolution(Decimal(manual_unit_price), "MANUAL", None)
		if manual_unit_price is not None
		else resolve_sale_price(
			session, party, product, unit_id, Decimal(quantity), sale.channel, sale.sale_date
		)
	)
	if discount_pct < 0 or discount_pct > 1:
		raise SaleError("El descuento debe estar entre 0 y 1.")
	quantity_base = convert_quantity(
		session, quantity, unit_id, product.base_unit_id, product.id
	)
	gross = Decimal(quantity) * resolution.unit_price
	discount = _money(gross * discount_pct)
	subtotal = _money(gross - discount)
	tax = product.tax if product.tax and product.tax.applies_on(sale.sale_date) else None
	tax_rate = Decimal(tax.rate) if tax is not None else Decimal("0")
	tax_amount = _money(subtotal * tax_rate)
	item = SaleItem(
		sale=sale,
		line_no=len(sale.items) + 1,
		product_id=product.id,
		description=product.name,
		quantity=quantity,
		unit_id=unit_id,
		quantity_base=quantity_base,
		unit_price=resolution.unit_price,
		price_list_item_id=resolution.price_list_item_id,
		price_source=resolution.price_source,
		discount_pct=discount_pct,
		discount_amount=discount,
		tax_id=tax.id if tax else None,
		tax_rate=tax_rate,
		tax_amount=tax_amount,
		subtotal=subtotal,
		total=_money(subtotal + tax_amount),
	)
	session.add(item)
	_recalculate_sale(sale)
	session.flush()
	return item


def allocate_sale_item_batches(
	session: Session,
	item: SaleItem,
	allocations: list[dict],
	*,
	created_by_id: int | None = None,
) -> list[SaleItemBatch]:
	if item.sale is not None and not item.sale.is_editable:
		raise SaleError("La venta no esta editable.")
	if item.batch_allocations:
		raise SaleError("La linea ya tiene lotes asignados.")
	result = []
	total = Decimal("0")
	for allocation in allocations:
		quantity_base = Decimal(str(allocation["quantity_base"]))
		batch_id = allocation["batch_id"]
		location_id = allocation["location_id"]
		try:
			movement = create_outbound_movement(
				session,
				product_id=item.product_id,
				location_id=location_id,
				batch_id=batch_id,
				quantity=quantity_base,
				unit_id=item.unit_id,
				quantity_base=quantity_base,
				reference_type="SALE_ITEM_BATCH",
				reference_id=item.id,
				created_by_id=created_by_id,
			)
		except InventoryError as exc:
			raise SaleError(str(exc)) from exc
		row = SaleItemBatch(
			batch_id=batch_id,
			location_id=location_id,
			quantity=quantity_base,
			unit_id=item.unit_id,
			quantity_base=quantity_base,
			unit_cost=movement.unit_cost or 0,
			total_cost=movement.total_cost or 0,
			movement_id=movement.id,
		)
		item.batch_allocations.append(row)
		result.append(row)
		total += quantity_base
	session.flush()
	if total != Decimal(item.quantity_base):
		raise SaleError("La suma de lotes no coincide con la cantidad de la linea.")
	return result


def confirm_sale(session: Session, sale: Sale) -> Sale:
	if not sale.is_editable or not sale.items:
		raise SaleError("La venta debe ser un borrador con lineas.")
	total_cost = Decimal("0")
	for item in sale.items:
		if not item.is_batch_allocation_balanced:
			raise SaleError(f"La linea {item.line_no} no esta balanceada por lotes.")
		line_cost = sum(
			(Decimal(row.total_cost) for row in item.batch_allocations), Decimal("0")
		)
		total_cost += line_cost
		item.unit_cost = (
			line_cost
			/ Decimal(item.quantity_base)
		)
		item.total_cost = _money(line_cost)
		item.margin_amount = _money(Decimal(item.total) - Decimal(item.total_cost))
	sale.cost_total = _money(total_cost)
	sale.margin_amount = _money(Decimal(sale.total) - sale.cost_total)
	sale.margin_pct = sale.margin_amount / sale.total if sale.total else None
	sale.status = "CONFIRMED"
	sale.confirmed_at = datetime.now(timezone.utc)
	session.flush()
	return sale


def cancel_sale(
	session: Session,
	sale: Sale,
	*,
	reason: str,
	created_by_id: int | None = None,
	notify_telegram: bool = True,
	cancelled_by_name: str | None = None,
) -> Sale:
	"""Cancelar una venta y revertir sus efectos.
	
	Características:
	- Solo cancela ventas en DRAFT o CONFIRMED
	- Revierte automáticamente movimientos de inventario si está CONFIRMED
	- Notifica a Telegram del evento
	- Permite devoluciones futuras referenciando la venta original
	
	Args:
		session: Sesión SQLAlchemy
		sale: Venta a cancelar
		reason: Razón de la cancelación
		created_by_id: ID del usuario que cancela (para auditoría)
		notify_telegram: Si enviar notificación a Telegram
		cancelled_by_name: Nombre/email del usuario que cancela (para Telegram)
		
	Returns:
		Sale: La venta cancelada
		
	Raises:
		SaleError: Si la venta no puede ser cancelada
	"""
	if sale.status not in ("DRAFT", "CONFIRMED"):
		raise SaleError("Solo se puede cancelar una venta abierta o confirmada.")
	
	if sale.status == "CONFIRMED":
		from app.services.inventory_service import reverse_movement

		for item in sale.items:
			for allocation in item.batch_allocations:
				if allocation.movement_id is not None:
					reverse_movement(session, allocation.movement_id, created_by_id=created_by_id)
	
	sale.status = "CANCELLED"
	sale.cancelled_at = datetime.now(timezone.utc)
	sale.cancellation_reason = reason
	session.flush()
	
	# Notificar a Telegram si está configurado
	if notify_telegram:
		try:
			from app.services.telegram_service import notify_sale_cancelled, TelegramError
			notify_sale_cancelled(
				sale,
				reason=reason,
				cancelled_by=cancelled_by_name
			)
		except TelegramError:
			# No fallar la cancelación si Telegram no funciona
			import logging
			logger = logging.getLogger(__name__)
			logger.warning(
				f"No se pudo notificar cancelación de venta {sale.sale_number} a Telegram"
			)
	
	return sale


def delete_sale(
	session: Session,
	sale: Sale,
	*,
	created_by_id: int | None = None,
) -> None:
	"""DEPRECADO: Usar cancel_sale() en su lugar.
	
	Esta función se mantiene por compatibilidad pero realiza una cancelación
	en lugar de una eliminación física. Las ventas nunca se deben eliminar,
	solo cancelar para mantener historial.
	"""
	# Simplemente cancelar sin notificación (mantiene compatibilidad)
	cancel_sale(
		session,
		sale,
		reason="Cancelado por API legacy",
		created_by_id=created_by_id,
		notify_telegram=False
	)


__all__ = [
	"PriceResolution",
	"SaleError",
	"add_sale_item",
	"allocate_sale_item_batches",
	"cancel_sale",
	"confirm_sale",
	"create_sale",
	"resolve_sale_price",
]