"""Traslados entre bodegas: origen → tránsito → destino."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from decimal import Decimal

from flask import current_app
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.inventory import InventoryLocation
from app.models.product import Product
from app.models.shipment import Shipment, ShipmentEvent, ShipmentItem
from app.services.inventory_service import InventoryError, create_transfer


def _transit(session: Session) -> InventoryLocation:
    code = current_app.config.get("TRANSIT_LOCATION_CODE", "TRANSITO")
    loc = session.scalar(
        select(InventoryLocation).where(
            InventoryLocation.code == code,
            InventoryLocation.location_type == "IN_TRANSIT",
        )
    )
    if loc is None:
        raise InventoryError(f"Crea la ubicación IN_TRANSIT con código {code}.")
    return loc


def _warehouse(session: Session, location_id: int) -> InventoryLocation:
    loc = session.get(InventoryLocation, location_id)
    if loc is None or loc.location_type != "WAREHOUSE" or not loc.is_active:
        raise InventoryError("Origen y destino deben ser bodegas activas.")
    return loc


def _tag(movements, shipment_id: int) -> None:
    for m in movements:
        m.reference_type = "TRANSFER"
        m.reference_id = shipment_id


def dispatch_transfer(
    session: Session, *, from_location_id: int, to_location_id: int,
    lines: list[dict], carrier_name: str | None = None,
    tracking_number: str | None = None, freight_cost: Decimal = Decimal(0),
    user_id: int | None = None, notes: str | None = None,
) -> Shipment:
    """lines: [{'product_id', 'batch_id', 'quantity'}] en unidad base."""
    if not lines:
        raise InventoryError("Indica la cantidad de al menos un producto.")
    if from_location_id == to_location_id:
        raise InventoryError("El origen y el destino deben ser distintos.")

    origin = _warehouse(session, from_location_id)
    _warehouse(session, to_location_id)
    transit = _transit(session)
    now = datetime.now(timezone.utc)

    shipment = Shipment(
        shipment_number=f"TMP-{uuid.uuid4().hex[:12]}",
        shipment_type="TRANSFER",
        origin_location_id=from_location_id,
        destination_location_id=to_location_id,
        carrier_name=carrier_name,
        tracking_number=tracking_number,
        status="DISPATCHED",
        dispatched_at=now,
        freight_cost=freight_cost,
        notes=notes,
        created_by_id=user_id,
    )
    session.add(shipment)
    session.flush()
    shipment.shipment_number = f"TRF-{shipment.id:05d}"

    for ln in lines:
        product = session.get(Product, ln["product_id"])
        if product is None:
            raise InventoryError("Un producto del traslado no existe.")
        qty = Decimal(ln["quantity"])
        out, inn = create_transfer(
            session, product_id=product.id, batch_id=ln["batch_id"],
            from_location_id=from_location_id, to_location_id=transit.id,
            quantity=qty, unit_id=product.base_unit_id, quantity_base=qty,
            occurred_at=now, created_by_id=user_id,
            notes=f"Traslado {shipment.shipment_number}",
        )
        _tag((out, inn), shipment.id)
        session.add(ShipmentItem(
            shipment_id=shipment.id, product_id=product.id,
            batch_id=ln["batch_id"], quantity=qty,
            unit_id=product.base_unit_id, quantity_base=qty,
            movement_id=out.id,
        ))

    session.add(ShipmentEvent(
        shipment_id=shipment.id, event_type="DISPATCHED",
        location_text=origin.name, message="Traslado despachado.",
        created_by_id=user_id,
    ))
    session.flush()
    return shipment


def receive_transfer(
    session: Session, shipment_id: int, *,
    user_id: int | None = None, received_by: str | None = None,
) -> Shipment:
    shipment = session.get(Shipment, shipment_id, with_for_update=True)
    if shipment is None or shipment.shipment_type != "TRANSFER":
        raise InventoryError("El traslado no existe.")
    if shipment.status not in ("DISPATCHED", "IN_TRANSIT"):
        raise InventoryError("Este traslado ya fue cerrado.")

    transit = _transit(session)
    now = datetime.now(timezone.utc)
    for item in shipment.items:
        out, inn = create_transfer(
            session, product_id=item.product_id, batch_id=item.batch_id,
            from_location_id=transit.id,
            to_location_id=shipment.destination_location_id,
            quantity=item.quantity, unit_id=item.unit_id,
            quantity_base=item.quantity_base, occurred_at=now,
            created_by_id=user_id,
            notes=f"Recepción {shipment.shipment_number}",
        )
        _tag((out, inn), shipment.id)

    shipment.status = "DELIVERED"
    shipment.delivered_at = now
    shipment.received_by = received_by
    session.add(ShipmentEvent(
        shipment_id=shipment.id, event_type="DELIVERED",
        message="Traslado recibido en destino.", created_by_id=user_id,
    ))
    session.flush()
    return shipment