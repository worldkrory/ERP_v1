"""Entrega física ya realizada: traslado de custodia, NO consumo productivo.
No llama commit: la ruta confirma toda la operación una sola vez.
"""
import json
from datetime import datetime, timezone
from decimal import Decimal
from sqlalchemy import select
from app.models.batch import Batch
from app.models.inventory import InventoryBalance, InventoryLocation
from app.models.product import Product
from app.models.production import ProductionOrder, ProcessExecution, ProductionProcess
from app.models.unit import UnitOfMeasure
from app.services.inventory_service import create_transfer
from app.services.costing import resolve_outbound_cost

MARK = 'DN_MAQUILA_V1:'

def read_snapshot(order):
    if not (order.notes or '').startswith(MARK):
        return None
    try:
        return json.loads(order.notes[len(MARK):])
    except (ValueError, TypeError):
        return None

def history(session, processor_id, process_id):
    rows = session.scalars(select(ProcessExecution).where(
        ProcessExecution.executor_party_id == processor_id,
        ProcessExecution.process_id == process_id,
        ProcessExecution.status.in_(['RECEIVED', 'DONE']),
        ProcessExecution.input_quantity_base > 0,
        ProcessExecution.output_quantity_base > 0,
    ).order_by(ProcessExecution.received_at.desc(), ProcessExecution.id.desc()).limit(20)).all()
    # Son referencias de peso, no costos ni modelos de aprendizaje automático.
    return [{'id':r.id, 'input':str(r.input_quantity_base), 'output':str(r.output_quantity_base)} for r in rows]

def deliver(session, *, number, origin_id, processor_id, process_id, lines, when, snapshot, user_id):
    existing = session.scalar(select(ProductionOrder).where(ProductionOrder.order_number == number))
    if existing:
        if read_snapshot(existing) == snapshot:
            return existing
        raise ValueError('Este número de orden ya existe. Abre la orden antes de intentar otra entrega.')
    origin = session.get(InventoryLocation, origin_id)
    destination = session.get(InventoryLocation, processor_id)
    process = session.get(ProductionProcess, process_id)
    if not origin or not origin.is_active or origin.location_type != 'WAREHOUSE':
        raise ValueError('Selecciona una bodega de origen activa.')
    if not destination or not destination.is_active or destination.location_type != 'PROCESSOR' or not destination.party_id:
        raise ValueError('La ubicación de maquila debe ser PROCESSOR, activa y asociada al tercero.')
    if origin.id == destination.id or not process or not process.is_active:
        raise ValueError('Origen, destino o proceso inválidos.')
    kgunit = session.scalar(select(UnitOfMeasure).where(UnitOfMeasure.code == 'KG'))
    if not kgunit:
        raise ValueError('No existe la unidad KG.')
    validated=[]
    # Orden estable de bloqueos para solicitudes concurrentes.
    for bid, qty in sorted(lines):
        batch = session.scalar(select(Batch).where(Batch.id == bid).with_for_update())
        product = session.get(Product, batch.product_id) if batch else None
        if not batch or batch.status != 'ACTIVE' or not product or not product.is_active:
            raise ValueError('Un lote no existe o no está activo.')
        if product.product_kind != 'RAW_MATERIAL' or batch.unit_id != kgunit.id or product.base_unit_id != kgunit.id:
            raise ValueError('Esta entrega admite materia prima registrada en KG. No se asumen conversiones.')
        balance = session.scalar(select(InventoryBalance).where(
            InventoryBalance.batch_id == bid, InventoryBalance.product_id == product.id,
            InventoryBalance.location_id == origin.id).with_for_update())
        if not balance or balance.quantity_base < qty:
            raise ValueError(f'Saldo insuficiente para {batch.batch_code}.')
        cost = resolve_outbound_cost(session, product.id, bid, origin.id, qty)
        # No perpetuar diferencias históricas de valorización ni cambiar política silenciosamente.
        expected = Decimal(batch.unit_cost)
        if abs(cost.unit_cost - expected) > Decimal('0.0001') or abs(
            Decimal(balance.total_value) - Decimal(balance.quantity_base)*expected) > Decimal('0.02'):
            raise ValueError(f'{batch.batch_code}: costo de lote y saldo no conciliados. La entrega no se registró; concilia primero la valorización.')
        validated.append((batch, product, qty))
    order = ProductionOrder(order_number=number, status='IN_PROGRESS', started_at=when,
        currency='COP', notes=MARK+json.dumps(snapshot, ensure_ascii=False), created_by_id=user_id)
    session.add(order); session.flush()
    session.add(ProcessExecution(production_order_id=order.id, process_id=process.id, sequence_no=1,
        executor_type='EXTERNAL', executor_party_id=destination.party_id, location_id=destination.id,
        status='SENT', sent_at=when, input_quantity_base=sum(q for _,_,q in validated), currency='COP',
        notes='Entrega de custodia; no confirma consumo ni producto terminado.', created_by_id=user_id))
    for batch, product, qty in validated:
        out, inn = create_transfer(session, product_id=product.id, batch_id=batch.id,
            from_location_id=origin.id, to_location_id=destination.id,
            quantity=qty, quantity_base=qty, unit_id=kgunit.id, occurred_at=when,
            created_by_id=user_id, notes=f'Maquila {number}; orden {order.id}; entrega de custodia')
        # create_transfer ya deja el par de movimientos enlazado entre sí.
        # La vinculación con esta orden queda en el snapshot + notas, sin FK ficticia.
    session.flush()
    return order
