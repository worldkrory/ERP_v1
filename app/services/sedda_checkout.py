"""Adaptador de /checkout/cotizar. SELECT de inventario y sesión; sin INSERT/UPDATE.
El snapshot de sesión NO es una reserva ni un pedido. Antes de pagar debe llamarse
require_valid_quote y crear la reserva/pedido de forma atómica en su servicio propio.
"""
import os
import secrets
import time
from decimal import Decimal
from flask import current_app, request, session, render_template
from sqlalchemy.exc import SQLAlchemyError
from app.extensions import db
from app.services.cart_service import get_cart, CART_SESSION_KEY
from app.services.shipping_service import get_city
from app.services.sedda_core import QuoteError, package, fingerprint, number, dane
from app.services.sedda_client import quote
from app.services.sedda_origins import select_origin

KEY='sedda_checkout_quote'
HEADERS={'Cache-Control':'no-store','Vary':'Cookie, HX-Request','X-Content-Type-Options':'nosniff'}

def ensure_token():
    if not session.get('shipping_csrf'):
        session['shipping_csrf']=secrets.token_urlsafe(32)
    return session['shipping_csrf']

def _clear():
    session.pop(KEY,None); session.pop('checkout_origin_id',None)

def _config():
    # Usar la misma lista de bodegas que ya utiliza la tienda.
    ids = current_app.config.get(
        "STOREFRONT_STOCK_LOCATION_IDS",
        (),
    )

    print("STOREFRONT_STOCK_LOCATION_IDS:", ids)

    if isinstance(ids, str):
        ids = tuple(
            int(value.strip())
            for value in ids.split(",")
            if value.strip()
        )
    else:
        ids = tuple(int(value) for value in (ids or ()))

    token = (
        current_app.config.get("SEDDA_API_TOKEN")
        or os.getenv("SEDDA_API_TOKEN", "")
    )

    return ids, token

def _cart():
    before=dict(session.get(CART_SESSION_KEY,{}) or {})
    cart=get_cart()
    if before!=dict(session.get(CART_SESSION_KEY,{}) or {}):
        raise QuoteError('Cambió la disponibilidad de tu carrito. Revisa tu taza antes de continuar.')
    if not cart['items']:raise QuoteError('Tu carrito está vacío.')
    if len(cart['items'])>50:raise QuoteError('Este pedido requiere cotización asistida.')
    return cart

def _basis(cart,dest):
    ids,token=_config()
    policy={'mode':'fixed-manizales','origin_dane':'17001000',
        'carrier':current_app.config.get('SEDDA_CARRIER','coordinadora'),
        'floor':str(number(current_app.config.get('SHIPPING_MIN_CHARGE_COP',0))),
        'free':bool(cart['qualifies_for_free_shipping'])}
    pack=package(cart,current_app.config.get('STOREFRONT_BAG_TARE_G',30),
        current_app.config.get('STOREFRONT_BOX_TARE_G',150))
    reader=current_app.extensions.get('checkout_reserved_base_reader')
    origin=select_origin(db.session,cart,ids,reader)
    
    fp=fingerprint(cart,dest,origin.id,pack,policy)
    return token,policy,pack,origin,fp

def quote_response():
    supplied=request.headers.get('X-Shipping-CSRF','')
    expected=session.get('shipping_csrf','')
    if not expected or not secrets.compare_digest(supplied,expected):
        _clear()
        return render_template('storefront/_sedda_quote.html',error='La sesión de envío venció. Recarga el checkout.'),403,HEADERS
    try:
        city=get_city(request.form.get('ciudad_codigo',''))
        if not city:raise QuoteError('Selecciona una ciudad del listado.')
        dest=dane(city['codigo']); cart=_cart()
        token,policy,pack,origin,fp=_basis(cart,dest)
        ttl=int(current_app.config.get('SEDDA_CHECKOUT_TTL_SECONDS',300))
        if not 30<=ttl<=900:raise QuoteError('La vigencia del checkout requiere revisión.')
        now=time.time(); old=session.get(KEY)
        # Solo mismo carrito, política, destino y bodega, con validación de stock en cada consulta.
        if old and old.get('fingerprint')==fp and 0<=now-old.get('created_at',0)<ttl:
            return render_template('storefront/_sedda_quote.html',q=old,error=None),200,HEADERS
        _clear()
        if now-float(session.get('sedda_last_request',0))<3:
            raise QuoteError('Espera unos segundos antes de volver a cotizar.')
        session['sedda_last_request']=now
        reply=quote(token=token,destination=dest,pack=pack,carrier=policy['carrier'])
        cost=number(reply['price'],positive=True)
        charged=Decimal(0) if policy['free'] else max(cost,number(policy['floor']))
        q={'schema':1,'fingerprint':fp,'created_at':now,'expires_at':now+ttl,
            'quote_id':reply['id'],'origin_id':origin.id,'origin_code':origin.code,
            'origin_dane':'17001000','destination_dane':dest,'destination_name':city['nombre'],
            'carrier':reply['carrier'],'days':reply['days'],'pack':pack,
            'subtotal':str(cart['subtotal']),'real_cost':str(cost),'shipping':str(charged),
            'total':str(number(cart['subtotal'])+charged),'free':policy['free']}
        session[KEY]=q;session['checkout_origin_id']=origin.id
        return render_template('storefront/_sedda_quote.html',q=q,error=None),200,HEADERS
    except QuoteError as exc:
        _clear()
        # Se devuelven errores de negocio en HTML 200 para reemplazar también la tarifa anterior.
        return render_template('storefront/_sedda_quote.html',error=str(exc)),200,HEADERS
    except (SQLAlchemyError,ValueError,TypeError):
        db.session.rollback();_clear()
        current_app.logger.warning('Cotización Sedda no disponible: revisar configuración/inventario (sin datos sensibles)')
        return render_template('storefront/_sedda_quote.html',error='No pudimos validar el envío. Inténtalo más tarde.'),200,HEADERS

def require_valid_quote(destination):
    """Para el FUTURO servicio de pedido/pago. No constituye reserva de stock."""
    q=session.get(KEY)
    if not q or q.get('schema')!=1 or time.time()>=q.get('expires_at',0):
        _clear();raise QuoteError('Cotiza de nuevo antes de continuar.')
    dest=dane(destination)
    if dest!=q['destination_dane']:
        _clear();raise QuoteError('Cambió el destino; debes cotizar de nuevo.')
    _,_,_,_,fp=_basis(_cart(),dest)
    if not secrets.compare_digest(fp,q['fingerprint']):
        _clear();raise QuoteError('Cambió el carrito, bodega o tarifa comercial; debes cotizar de nuevo.')
    return dict(q)
