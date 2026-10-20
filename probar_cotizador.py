import sys, uuid
from datetime import datetime, timedelta, timezone
import requests

URL = "https://interrapidisimo.com/api/cotizador/cotizar"
destino = sys.argv[1] if len(sys.argv) > 1 else "18753000"
origen = sys.argv[2] if len(sys.argv) > 2 else "17001000"

fecha = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat(
    timespec="milliseconds").replace("+00:00", "Z")

for forma, contra in ((1, False), (3, False), (3, True)):
    sid = "36d870d9-e8b4-455d-8bf6-53d8e0d5a37b"
    body = {"guid": sid, "payload": {
        "fecha": fecha, "documentoRemitente": "", "documentoDestinatario": "",
        "esInterPay": False, "idCiudadOrigen": origen, "idCiudadDestino": destino,
        "largo": 0, "alto": 0, "ancho": 0, "pesoBascula": 1, "valorDeclarado": 86000,
        "idTipoEntrega": "1", "idFormaPago": forma, "aplicaContraPago": contra}}
    r = requests.post(URL, json=body, timeout=10, headers={
        "accept": "*/*", "content-type": "application/json", "x-session-id": sid})
    print(f"\nformaPago={forma} contraPago={contra} -> {r.status_code}")
    print(r.text[:1200])