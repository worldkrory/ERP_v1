import json, secrets, uuid
from datetime import date, datetime, timezone, timedelta
from decimal import Decimal
from flask import render_template, request, session, abort, redirect, url_for, current_app
from flask_login import login_required, current_user
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from app.extensions import db
from app.auth.decorators import require_role
from app.maquila import maquila_bp
from app.maquila.domain import decimal_value, business_due, forecast
from app.maquila.service import deliver, history, read_snapshot, MARK
from app.models.production import ProductionOrder, ProductionProcess
from app.models.inventory import InventoryLocation, InventoryBalance
from app.models.batch import Batch
from app.models.product import Product
from app.models.unit import UnitOfMeasure

HEADERS={'Cache-Control':'no-store', 'Vary':'HX-Request'}

def csrf():
    if 'maquila_csrf' not in session:
        session['maquila_csrf']=secrets.token_urlsafe(32)
    return session['maquila_csrf']

def catalog():
    locations=db.session.scalars(select(InventoryLocation).where(InventoryLocation.is_active.is_(True))).all()
    return dict(origins=[x for x in locations if x.location_type=='WAREHOUSE'],
        processors=[x for x in locations if x.location_type=='PROCESSOR' and x.party_id],
        processes=db.session.scalars(select(ProductionProcess).where(ProductionProcess.is_active.is_(True))).all(),
        batches=db.session.execute(
            select(
                Batch.id.label("id"),
                Batch.batch_code.label("batch_code"),
                Product.name.label("product_name"),
                Batch.initial_quantity.label("initial_quantity"),
                InventoryBalance.location_id.label("location_id"),
                InventoryBalance.quantity_base.label("available_quantity"),
            )
            .join(Product, Product.id == Batch.product_id)
            .join(
                InventoryBalance,
                (InventoryBalance.batch_id == Batch.id)
                & (InventoryBalance.product_id == Product.id),
            )
            .join(
                UnitOfMeasure,
                UnitOfMeasure.id == Product.base_unit_id,
            )
            .where(
                Batch.status == "ACTIVE",
                Product.is_active.is_(True),
                Product.product_kind == "RAW_MATERIAL",
                UnitOfMeasure.code == "KG",
                Batch.unit_id == Product.base_unit_id,
                InventoryBalance.quantity_base > 0,
            )
            .order_by(Batch.batch_code, InventoryBalance.location_id)
        ).mappings().all())

def parsed():
    f=request.form
    origin=int(f.get('origin_id','0')); processor=int(f.get('processor_id','0')); process=int(f.get('process_id','0'))
    when=date.fromisoformat(f.get('delivered_on',''))
    if when>date.today(): raise ValueError('La entrega debe haber ocurrido; no se aceptan entregas futuras.')
    days=int(f.get('days','5'))
    if not 1<=days<=60: raise ValueError('El plazo debe ser de 1 a 60 días de lunes a viernes.')
    grams=decimal_value(f.get('grams','340'))
    q=decimal_value(f.get('quote')) if f.get('quote','').strip() else None
    bids=f.getlist('batch_id'); quantities=f.getlist('kg')
    if len(bids)!=len(quantities): raise ValueError('Líneas incompletas.')
    lines=[]
    for bid,kg in zip(bids,quantities):
        if not bid and not kg: continue
        qty=decimal_value(kg)
        if qty!=qty.quantize(Decimal('0.0001')): raise ValueError('Máximo 4 decimales en los kilos.')
        lines.append((int(bid),qty))
    if not lines or len(lines)>20 or len({b for b,_ in lines})!=len(lines):
        raise ValueError('Indica entre 1 y 20 lotes distintos, sin repetir.')
    loc=db.session.get(InventoryLocation, processor)
    if not loc or loc.location_type!='PROCESSOR' or not loc.party_id: raise ValueError('Maquilador inválido.')
    h=history(db.session,loc.party_id,process)
    predicted=forecast(sum(x[1] for x in lines),h,grams,q)
    snap={'version':1, 'delivered_on':when.isoformat(), 'due_on':business_due(when,days).isoformat(),
        'calendar':'lunes-viernes SIN festivos', 'origin_id':origin, 'processor_id':processor,'process_id':process,
        'lines':[{'batch_id':b,'kg':str(k)} for b,k in lines], 'forecast':predicted,'history':h,
        'reference':f.get('reference','').strip()[:120], 'notes':f.get('notes','').strip()[:1000]}
    return origin,processor,process,lines,when,snap

@maquila_bp.get('/produccion/maquilas')
@login_required
@require_role('INVENTARIO','ADMIN')
def board():
    orders=db.session.scalars(select(ProductionOrder).where(ProductionOrder.notes.like(MARK+'%')).order_by(ProductionOrder.id.desc()).limit(100)).all()
    rows=[{'order':o,'s':read_snapshot(o)} for o in orders if read_snapshot(o)]
    return render_template('maquila/board.html',rows=rows,today=date.today().isoformat()),200,HEADERS

@maquila_bp.get('/produccion/maquilas/nueva')
@login_required
@require_role('INVENTARIO','ADMIN')
def new():
    return render_template('maquila/new.html',**catalog(),csrf=csrf(),today=date.today().isoformat(),
        number='MQ-'+uuid.uuid4().hex[:20],writes=current_app.config.get('MAQUILA_DELIVERY_ENABLED',False)),200,HEADERS

@maquila_bp.post('/produccion/maquilas/pronostico')
@login_required
@require_role('INVENTARIO','ADMIN')
def preview():
    try:
        *_, snap=parsed()
        return render_template('maquila/forecast.html',s=snap),200,HEADERS
    except (ValueError,ArithmeticError) as e:
        return render_template('maquila/error.html',message=str(e)),422,HEADERS

@maquila_bp.post('/produccion/maquilas/entregar')
@login_required
@require_role('INVENTARIO','ADMIN')
def submit():
    if not current_app.config.get('MAQUILA_DELIVERY_ENABLED',False): abort(403)
    if not secrets.compare_digest(request.form.get('csrf',''),session.get('maquila_csrf','!')): abort(403)
    if request.form.get('confirmed')!='yes': abort(400)
    try:
        origin,processor,process,lines,when,snap=parsed()
        number=request.form.get('number','')
        if not number.startswith('MQ-') or len(number)>30: raise ValueError('Número inválido.')
        order=deliver(db.session,number=number,origin_id=origin,processor_id=processor,process_id=process,
            lines=lines,when=datetime.combine(when,datetime.min.time(),tzinfo=timezone(timedelta(hours=-5))),
            snapshot=snap,user_id=current_user.id)
        db.session.commit()
        return redirect(url_for('maquila.detail',order_id=order.id),code=303)
    except (ValueError,ArithmeticError) as e:
        db.session.rollback()
        return render_template('maquila/error.html',message=str(e)),422,HEADERS
    except SQLAlchemyError:
        db.session.rollback();current_app.logger.exception('Entrega de maquila revertida')
        return render_template('maquila/error.html',message='No se guardó la entrega. Revisa si ya existe la orden antes de reintentar.'),409,HEADERS

@maquila_bp.get('/produccion/maquilas/<int:order_id>')
@login_required
@require_role('INVENTARIO','ADMIN')
def detail(order_id):
    o=db.session.get(ProductionOrder,order_id)
    s=read_snapshot(o) if o else None
    if not s: abort(404)
    lines=[]
    for ln in s['lines']:
        b=db.session.get(Batch,ln['batch_id'])
        lines.append({'code':b.batch_code if b else ln['batch_id'],'kg':ln['kg']})
    return render_template('maquila/detail.html',o=o,s=s,lines=lines),200,HEADERS
