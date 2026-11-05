"""Contrato de cotización Sedda. Funciones puras; nunca escribe en base de datos."""
import hashlib
import json
import re
import unicodedata
from decimal import Decimal, InvalidOperation, ROUND_CEILING

class QuoteError(ValueError):
    pass

def number(value, *, positive=False):
    try:
        result=Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        raise QuoteError('Valor numérico inválido.')
    if not result.is_finite() or result<0 or (positive and result==0):
        raise QuoteError('El valor debe ser finito y no negativo.')
    return result

def dane(value):
    value=str(value or '').strip()
    if not re.fullmatch(r'\d{5}(?:000)?',value):
        raise QuoteError('Selecciona un municipio válido del catálogo.')
    return value[:5]+'000'

def normalized(value):
    value=unicodedata.normalize('NFKD',str(value or ''))
    return ''.join(c for c in value if not unicodedata.combining(c)).lower().strip()

def package(cart, bag_tare_g=30, box_tare_g=150):
    items=cart.get('items') or []
    if not items:
        raise QuoteError('Tu carrito está vacío.')
    net=Decimal(0); units=0
    tare=number(bag_tare_g); box=number(box_tare_g)
    for item in items:
        q=number(item.get('quantity'),positive=True)
        if q!=q.to_integral_value():
            raise QuoteError('Las cantidades de bolsas deben ser enteras.')
        grams=item.get('variant',{}).get('weight_g')
        if grams is None:
            raise QuoteError('Una presentación no tiene contenido neto configurado. No se asumirá un peso.')
        net+=number(grams,positive=True)*q; units+=int(q)
    gross=(net+tare*units+box)/1000
    # Precisión explícita de transporte; redondear hacia arriba evita subdeclarar.
    weight=gross.quantize(Decimal('0.01'),rounding=ROUND_CEILING)
    if weight<=0 or weight>50:
        raise QuoteError('Sedda admite hasta 50 kg por esta cotización. Contáctanos para este pedido.')
    subtotal=number(cart.get('subtotal'),positive=True)
    if subtotal!=subtotal.to_integral_value():
        raise QuoteError('El total publicado debe estar normalizado a pesos COP enteros antes de cotizar.')
    return {'net_g':str(net),'gross_kg':str(gross),'weight_kg':str(weight),'declared':int(subtotal)}

def fingerprint(cart,destination,origin_id,pack,policy):
    items=sorted([{'id':int(i['product_id']),'q':str(i['quantity']),
        'price':str(i['unit_price']),'grams':str(i['variant'].get('weight_g'))} for i in cart['items']],key=lambda i:i['id'])
    payload={'items':items,'subtotal':str(cart['subtotal']),'destination':dane(destination),
        'origin_id':int(origin_id),'pack':pack,'policy':policy}
    return hashlib.sha256(json.dumps(payload,sort_keys=True,separators=(',',':')).encode()).hexdigest()

def validate_reply(data, expected_origin='17001000', destination=None):
    if not isinstance(data,dict):
        raise QuoteError('Sedda devolvió un formato inesperado.')
    if not isinstance(data.get('id'),str) or not 1<=len(data['id'])<=120:
        raise QuoteError('Sedda no devolvió una referencia de cotización válida.')
    expected=dane(expected_origin)
    actual=data.get('origen_dane')
    if actual is not None:
        if dane(actual)!=expected:
            raise QuoteError('La cuenta Sedda cotizó desde otra ciudad. No se utilizará esa tarifa.')
    elif expected!='17001000' or normalized(data.get('origen_ciudad'))!='manizales':
        raise QuoteError('No fue posible verificar el origen Manizales en la respuesta de Sedda.')
    if destination and data.get('destino_dane') is not None and dane(data['destino_dane'])!=dane(destination):
        raise QuoteError('El destino de la respuesta no coincide con el solicitado.')
    price=number(data.get('precio_sedda'),positive=True)
    if price!=price.to_integral_value():
        raise QuoteError('Tarifa COP no entera; requiere conciliación antes de mostrarla.')
    # Este checkout solo cotiza envío prepagado, no recaudo contraentrega.
    cod=number(data.get('cargo_cod',0))
    if cod!=0:
        raise QuoteError('Sedda agregó un cargo de contraentrega a un pedido sin recaudo. Revisa la configuración.')
    carrier=data.get('carrier')
    if carrier not in ('coordinadora','tcc'):
        raise QuoteError('Transportadora no reconocida en esta integración.')
    return {'id':data['id'],'carrier':carrier,'origin_dane':expected,'price':str(price),
        'days':str(data.get('dias_estimados') or 'Plazo no informado')[:120]}
