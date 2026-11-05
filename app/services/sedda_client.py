"""Solo POST /cotizar. No crea guías, no recauda y no debita billetera."""
import requests
from app.services.sedda_core import QuoteError, dane, validate_reply, number

URL='https://crm.sedda.co/api/agent/v1/cotizar'

def quote(*,token,destination,pack,carrier='coordinadora',http=None):
    if not token or any(c.isspace() for c in token):
        raise QuoteError('La integración de envíos no tiene una credencial válida configurada.')
    if carrier not in ('coordinadora','tcc'):
        raise QuoteError('Transportadora no configurada correctamente.')
    payload={'destino_dane':dane(destination),'peso_kg':float(pack['weight_kg']),
        'cod_monto':0,'valor_declarado':pack['declared'],'carrier':carrier}
    try:
        response=(http or requests).post(URL,json=payload,headers={
            'Authorization':'Bearer '+token,'Content-Type':'application/json','Accept':'application/json'},
            timeout=(3.05,10),allow_redirects=False)
    except requests.RequestException as exc:
        error_type = type(exc).__name__

        logger.warning(
            "Sedda: fallo de transporte HTTP; tipo=%s",
            error_type,
        )

        raise QuoteError(
            "No pudimos consultar el envío. "
            "Revisa el diagnóstico de conexión en el servidor."
        ) from None
    status=response.status_code
    if status==429:
        raise QuoteError('El servicio de envíos está temporalmente ocupado. Espera antes de reintentar.')
    if status in (401,403):
        raise QuoteError('El servicio de envíos requiere revisión de credenciales o permisos.')
    if status in (400,404,422):
        raise QuoteError('No se obtuvo una cotización válida para este destino y paquete.')
    if status!=200:
        raise QuoteError('No fue posible consultar el envío. No se aplicará una tarifa estimada.')
    try:
        data=response.json()
    except ValueError:
        raise QuoteError('Respuesta inválida del cotizador.') from None
    result=validate_reply(data,destination=destination)
    # Si devuelve el peso debe corresponder al paquete solicitado.
    if data.get('peso_kg') is not None:
        if abs(number(data['peso_kg'])-number(pack['weight_kg']))>number('0.01'):
            raise QuoteError('El peso cotizado no coincide con el solicitado.')
    return result
