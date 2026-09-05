"""Verificación de seguridad del entorno.

Ejecutar ANTES de cualquier flask db migrate / upgrade:

    python verificar_entorno.py

Confirma contra qué base de datos está apuntando la app y avisa si detecta
que el entorno local está conectado a producción.
"""

import os
import sys
from urllib.parse import urlparse

from dotenv import load_dotenv

load_dotenv()

HOSTS_LOCALES = {"localhost", "127.0.0.1", "::1"}


def enmascarar(url):
    """Oculta la contraseña para poder mostrar la URL sin filtrar secretos."""
    partes = urlparse(url)
    host = partes.hostname or "?"
    puerto = f":{partes.port}" if partes.port else ""
    base = (partes.path or "").lstrip("/") or "?"
    usuario = partes.username or "?"
    return f"{partes.scheme}://{usuario}:***@{host}{puerto}/{base}"


def main():
    entorno = os.getenv("FLASK_CONFIG", "development")
    dev_url = os.getenv("DEV_DATABASE_URL")
    prod_url = os.getenv("DATABASE_URL")

    print(f"FLASK_CONFIG       : {entorno}")
    print(f"DEV_DATABASE_URL   : {enmascarar(dev_url) if dev_url else 'NO DEFINIDA'}")
    print(f"DATABASE_URL       : {'PRESENTE' if prod_url else 'ausente (correcto)'}")
    print("-" * 60)

    errores = []

    if entorno == "development":
        if prod_url:
            errores.append(
                "DATABASE_URL esta definida en el entorno local. "
                "Eliminala del .env: cualquier migracion afectaria produccion."
            )
        if not dev_url:
            errores.append(
                "DEV_DATABASE_URL no esta definida. "
                "Configura la base de datos local antes de continuar."
            )
        elif urlparse(dev_url).hostname not in HOSTS_LOCALES:
            errores.append(
                f"DEV_DATABASE_URL apunta a '{urlparse(dev_url).hostname}', "
                "que no es un host local. Verifica que sea la base correcta."
            )

    if errores:
        print("BLOQUEADO. No ejecutes migraciones:\n")
        for error in errores:
            print(f"  - {error}")
        sys.exit(1)

    print("Entorno correcto. Es seguro ejecutar migraciones.")
    sys.exit(0)


if __name__ == "__main__":
    main()
