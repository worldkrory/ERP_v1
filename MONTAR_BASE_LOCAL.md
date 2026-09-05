# Montar la base local — ERP Densa Niebla

Objetivo: dejar las 50 tablas creadas en `densa_niebla_dev`, con historial de
Alembic limpio y reversible. Sin bases desechables ni pruebas de laboratorio: se
monta la base de verdad.

Todo desde `D:\GITHUB ARCHIVES\ERP_v1` con el entorno activo.

---

## Qué archivos entran

Del paquete, copia sobre tu proyecto:

| Archivo | Destino | Nota |
|---|---|---|
| `app/models/` (21 archivos) | `app/models/` | reemplaza completo |
| `app/extensions.py` | `app/extensions.py` | reemplaza |
| `migrations/env.py` | `migrations/env.py` | **reemplaza el que generó `flask db init`** |
| `migrations/versions/0001_extensiones.py` | igual ruta | nuevo |
| `migrations/versions/0002_esquema_inicial.py` | igual ruta | nuevo, 1.725 líneas |
| `validar_modelos.py`, `generar_migracion_inicial.py` | raíz | herramientas |

El `env.py` nuevo agrega `compare_type=True` y `compare_server_default=True`. Sin
eso, cambiar un `NUMERIC(16,4)` a `NUMERIC(18,6)` no genera migración y la base
se queda atrás sin avisar. En un sistema que maneja dinero eso no es aceptable.

---

## Paso 1 — Confirma que la app expone el metadata

Este es el error más común y el más difícil de diagnosticar: si `create_app()` no
importa los modelos, Alembic ve un metadata vacío y genera una migración que
borra todo. Verifica que en `app/__init__.py`, dentro de `create_app`, exista:

```python
from app import models  # noqa: F401  (registra las 50 tablas en el metadata)
```

Compruébalo sin levantar el servidor:

```powershell
python -c "from app import create_app; from app.extensions import db; app=create_app(); ctx=app.app_context(); ctx.push(); print('tablas en el metadata:', len(db.metadata.tables))"
```

Debe decir **50**. Si dice 0, falta ese import y no sigas.

## Paso 2 — Valida los modelos

```powershell
python validar_modelos.py
```

Las seis líneas deben salir en `[OK]`, incluida la nueva:

```
[OK] 594 nombres de restriccion e indice: unicos, ninguno pasa de 63 caracteres (el mayor: 62).
```

## Paso 3 — Crea la base, si no existe

```powershell
psql -U postgres -c "CREATE DATABASE densa_niebla_dev;"
```

Si ya existe y quieres partir de cero:

```powershell
psql -U postgres -c "DROP DATABASE IF EXISTS densa_niebla_dev;"
psql -U postgres -c "CREATE DATABASE densa_niebla_dev;"
```

## Paso 4 — Aplica las migraciones

```powershell
$env:FLASK_APP = "run.py"
flask db upgrade
```

Debe aplicar las dos en orden: `0001_extensiones` y luego `0002_esquema_inicial`.

Confirma en qué revisión quedó:

```powershell
flask db current
```

## Paso 5 — Verifica lo que quedó creado

```powershell
psql -U postgres -d densa_niebla_dev -c "SELECT count(*) AS tablas FROM information_schema.tables WHERE table_schema='public' AND table_type='BASE TABLE';"
psql -U postgres -d densa_niebla_dev -c "SELECT contype, count(*) FROM pg_constraint WHERE connamespace='public'::regnamespace GROUP BY contype ORDER BY contype;"
```

Esperado: **51 tablas** (las 50 más `alembic_version`), y en el segundo:
`c` (CHECK) varios cientos, `f` 202, `p` 50, `u` 37, y **`x` = 2**, que son las
dos `EXCLUDE`. Si `x` no aparece, las restricciones de no solapamiento no se
crearon y el historial de precios queda sin protección.

## Paso 6 — La prueba que de verdad importa

Que la migración no tenga deriva contra los modelos:

```powershell
flask db migrate -m "prueba de deriva"
```

Debe responder **`Sin cambios en el esquema: no se genero migracion.`** Si en
cambio crea un archivo, ábrelo: lo que aparezca ahí es una diferencia entre los
modelos y lo que se creó en la base. Bórralo y mándame el contenido.

Y que sea reversible:

```powershell
flask db downgrade base
flask db upgrade
```

Tiene que bajar a cero y volver a subir sin errores. Esto es lo que garantiza que
podrás recuperar producción si una migración sale mal.

---

## Cuando esto pase, la base local está lista

El siguiente paso es la siembra de datos maestros, que va **separada** de las
migraciones a propósito: una migración cambia estructura, la siembra carga
contenido, y mezclarlas hace imposible volver atrás una sin perder la otra.

```powershell
flask seed initial    # todavía no existe: es el siguiente entregable
```

Cargará las unidades de medida con sus factores, los impuestos, las categorías de
costo, los consecutivos de documentos y las 11 claves de `app_settings`,
incluyendo `default_costing_method`. Ahí entran los valores que quedaron
pendientes de confirmar con administración: factores de arroba, carga y saco, y
las tarifas de IVA e INC del café tostado.

## Telegram y comprobantes

La migración `0003_telegram_comprobantes` agrega la trazabilidad de
notificaciones y los enlaces de comprobantes. El archivo no guarda tokens: en
Heroku configura estas variables en **Settings → Config Vars**:

```powershell
heroku config:set TELEGRAM_BOT_TOKEN="<token-del-bot>"
heroku config:set TELEGRAM_CHAT_ID="<id-del-grupo>"
heroku config:set CLOUDINARY_CLOUD_NAME="<cloud-name>"
heroku config:set CLOUDINARY_API_KEY="<api-key>"
heroku config:set CLOUDINARY_API_SECRET="<api-secret>"
heroku config:set CLOUDINARY_FOLDER="densa-niebla/comprobantes"
```

El bot debe estar agregado al grupo y tener permiso para publicar mensajes.
Cada venta creada intenta enviar su número, cliente, total y canal. Para cargar
un comprobante se usa `POST /api/v1/payments/<payment_id>/receipt` como
`multipart/form-data`, con el archivo en el campo `receipt`; la respuesta incluye
`receipt_url` y el estado de revisión. Cloudinary conserva la imagen y Telegram
la muestra en el grupo usando `sendPhoto`.

El límite de subida es 10 MB. Telegram o Cloudinary pueden fallar sin borrar la
venta: el sistema registra el estado y deja el comprobante disponible cuando la
subida a Cloudinary sí tuvo éxito.

---

## Si algo falla

**`Target database is not up to date`** — hay una revisión aplicada que Alembic no
reconoce. Mira `flask db current` y `flask db history`.

**`Can't locate revision identified by ...`** — falta un archivo en
`migrations/versions/`. Confirma que estén los dos.

**`extension "btree_gist" does not exist`** — la migración `0001` no corrió. Corre
`flask db upgrade 0001_extensiones` sola y revisa el error.

**Alembic genera una migración que hace `drop_table` de todo** — es el caso del
paso 1: el metadata está vacío. Borra ese archivo sin aplicarlo.

**Un `CHECK` rechazado por PostgreSQL** — mándame la sentencia. Es lo único que
todavía no está verificado contra un motor real.

---

## Para regenerar la migración desde cero

Si cambias los modelos antes de aplicar nada:

```powershell
del migrations\versions\0002_esquema_inicial.py
python generar_migracion_inicial.py
```

El script la reconstruye desde el metadata y verifica que salgan las 50 tablas,
los 97 índices, las 2 `EXCLUDE` y los 8 índices parciales, en `upgrade` y en
`downgrade`. Después de que la base ya exista, no uses esto: usa
`flask db migrate`, que compara contra lo que hay creado.
