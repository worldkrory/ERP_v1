import requests, uuid
from datetime import datetime, timezone

def nueva_sesion():
    s = requests.Session()
    s.headers.update({"user-agent": "DensaNiebla-Checkout/1.0 (contacto@tudominio.com)"})
    s.get("https://interrapidisimo.com/cotiza-tu-envio", timeout=8)
    return s

def cotizar(s, destino, peso_kg, valor, origen="17001000"):
    sid = str(uuid.uuid4())
    body = {"guid": sid, "payload": {
        "fecha": datetime.now(timezone.utc).isoformat(),
        "documentoRemitente": "", "documentoDestinatario": "",
        "esInterPay": False, "idCiudadOrigen": origen, "idCiudadDestino": destino,
        "largo": 0, "alto": 0, "ancho": 0, "pesoBascula": peso_kg,
        "valorDeclarado": valor, "idTipoEntrega": "1", "idFormaPago": 1,
        "aplicaContraPago": False}}
    r = s.post("https://interrapidisimo.com/api/cotizador/cotizar",
               json=body, headers={"x-session-id": sid}, timeout=8)
    r.raise_for_status()
    return r.json()