"""Orígenes físicos elegibles. Por ahora solo Manizales; no hay aproximaciones geográficas.
No mueve stock. Hook reserved_reader(session, product_id, batch_id, location_id)
para integrar reservas persistentes cuando se implemente su servicio central.
"""
from datetime import date
from decimal import Decimal
from sqlalchemy import select
from app.models.batch import Batch
from app.models.inventory import InventoryBalance, InventoryLocation
from app.models.product import Product
from app.services.fulfillment_service import origin_dane_code
from app.services.units import convert_quantity, UnitConversionError
from app.services.sedda_core import QuoteError, number, dane

def select_origin(session,cart,allowed_ids,reserved_reader=None):
    
    if not allowed_ids:
        raise QuoteError('No hay bodegas habilitadas para despachar desde Manizales.')
    wanted={}
    for item in cart['items']:
        pid=int(item['product_id']); wanted[pid]=wanted.get(pid,Decimal(0))+number(item['quantity'],positive=True)
    products=session.scalars(select(Product).where(Product.id.in_(wanted))).all()
    if len(products)!=len(wanted):
        raise QuoteError('Uno de los productos ya no está disponible.')
    need={}
    for p in products:
        if not p.is_active or not p.is_sellable or not p.tracks_batches:
            raise QuoteError('Un producto no está habilitado para venta por lote.')
        try:
            factor=convert_quantity(session,Decimal(1),p.effective_sales_unit_id,p.base_unit_id,p.id)
        except UnitConversionError:
            raise QuoteError('Una presentación no tiene conversión de inventario válida.') from None
        need[p.id]=wanted[p.id]*number(factor,positive=True)
    locs=session.scalars(select(InventoryLocation).where(
        InventoryLocation.id.in_(allowed_ids),InventoryLocation.is_active.is_(True),
        InventoryLocation.location_type=='WAREHOUSE').order_by(InventoryLocation.code,InventoryLocation.id)).all()
    today=date.today()
    for loc in locs:
        code=origin_dane_code(loc)
        if not code or dane(code)!='17001000':continue
        rows=session.execute(select(InventoryBalance,Batch).join(Batch,Batch.id==InventoryBalance.batch_id).where(
            InventoryBalance.location_id==loc.id, InventoryBalance.product_id.in_(need),
            InventoryBalance.quantity_base>0, Batch.status=='ACTIVE',
            Batch.product_id==InventoryBalance.product_id)).all()
        stock={}
        for bal,batch in rows:
            if batch.expiry_date and batch.expiry_date<today:continue
            reserved=number(reserved_reader(session,bal.product_id,bal.batch_id,loc.id)) if reserved_reader else Decimal(0)
            free=max(Decimal(0),Decimal(bal.quantity_base)-reserved)
            stock[bal.product_id]=stock.get(bal.product_id,Decimal(0))+free
        if all(stock.get(pid,Decimal(0))>=amount for pid,amount in need.items()):
            return loc
    raise QuoteError('No hay una bodega habilitada en Manizales con todo tu pedido disponible. Ajusta las cantidades o contáctanos.')
