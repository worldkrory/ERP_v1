# Modelos SQLAlchemy — ERP Densa Niebla

**Estado:** escritos y verificados, **pendientes de tu aprobación**
**Base:** ERD lógico v1.0 aprobado
**Regla que sigue vigente:** no se genera ninguna migración hasta que apruebes esto

---

## Qué se entrega

| Archivo | Tablas | Líneas |
|---|---|---|
| `app/models/base.py` | — | 195 |
| `app/models/mixins.py` | — | 93 |
| `app/models/__init__.py` | — | 267 |
| `app/models/user.py` | `users`, `roles`, `user_roles` | 192 |
| `app/models/party.py` | `parties`, `party_roles`, `addresses`, `party_contacts` | 317 |
| `app/models/unit.py` | `units_of_measure`, `unit_conversions` | 205 |
| `app/models/tax.py` | `taxes` | 95 |
| `app/models/product.py` | `product_categories`, `products`, `coffee_profiles` | 364 |
| `app/models/price.py` | `price_lists`, `price_list_items`, `party_price_rules` | 320 |
| `app/models/intermediary.py` | `intermediary_fee_rules`, `intermediary_fee_entries` | 236 |
| `app/models/purchase.py` | `purchases`, `purchase_items` | 312 |
| `app/models/batch.py` | `batches`, `batch_lineage` | 319 |
| `app/models/inventory.py` | `inventory_locations`, `inventory_movements`, `inventory_balances` | 473 |
| `app/models/production.py` | los 6 de producción | 831 |
| `app/models/cost.py` | `cost_categories`, `cost_rules`, `cost_entries` | 443 |
| `app/models/sale.py` | `sales`, `sale_items`, `sale_item_batches` | 475 |
| `app/models/payment.py` | `payments`, `payment_allocations` | 218 |
| `app/models/invoice.py` | los 4 de facturación DIAN | 501 |
| `app/models/shipment.py` | `shipments`, `shipment_items`, `shipment_events` | 336 |
| `app/models/expense.py` | `expense_categories`, `expenses` | 247 |
| `app/models/setting.py` | `app_settings`, `document_sequences` | 194 |
| `app/extensions.py` | — | 42 |

Total: **50 tablas, 839 columnas, 6.675 líneas.**

Además, tres verificadores que puedes correr tú mismo:

- `validar_modelos.py` — mapeo, tipos, generación de DDL, orden de creación
- `auditar_vs_erd.py` — compara columna por columna contra el ERD en markdown
- `prueba_relaciones.py` — grafo de objetos en memoria, sin base de datos
- `probar_ddl_postgres.py` — crea el esquema en un PostgreSQL real y lo borra

Y dos archivos de apoyo: `ddl_generado.sql`, el SQL que producirían estos modelos
para que puedas leerlo antes de crear nada, y `ERD_Logico_Densa_Niebla_v1.md`, el
ERD aprobado, incluido aquí para que la auditoría tenga contra qué comparar sin
que tengas que buscarlo.

---

## Qué se verificó y qué no

### Verificado

```
[OK] Todos los mapeos se configuran sin error.
[OK] Tablas mapeadas: 50 (ERD espera 50)
[OK] DDL PostgreSQL generado: 150 sentencias
[OK] Orden de creacion resuelto para 50 tablas.
VALIDACION SUPERADA
```

- **839 columnas del ERD, cero omisiones** y cero columnas inventadas
  (`auditar_vs_erd.py` extrae las columnas de las tablas markdown del ERD y las
  contrasta contra `Base.metadata`).
- Ninguna clave primaria distinta de `BIGINT`. Ningún `FLOAT`, `REAL` ni
  `DOUBLE PRECISION` en todo el esquema. Ningún `TIMESTAMP` sin zona horaria.
- Cero `ENUM` nativos: los 209 `CHECK` cubren todos los dominios cerrados.
- Las 2 restricciones `EXCLUDE USING gist` de no solapamiento
  (`price_list_items_no_overlap`, `cost_rules_no_overlap`).
- Los 8 índices únicos parciales, incluido `uq_addresses_one_primary`,
  `uq_inventory_balances_no_batch` y `uq_invoices_cufe`.
- 202 claves foráneas, **todas con `ondelete` explícito**.
- 37 `UNIQUE`, 97 índices.
- Grafo de objetos navegable en ambos sentidos: un tercero con dos roles, un
  blend con dos lotes de origen, y una venta cuya línea se surte de dos lotes.

### NO verificado — y esto importa

**El DDL no se ejecutó contra un PostgreSQL real.** El sandbox donde trabajé no
permite instalar un servidor de base de datos. Lo que se validó es que
SQLAlchemy **compila** el DDL con el dialecto real de PostgreSQL, que es fuerte
pero no equivale a ejecutarlo. Quedan dos clases de error que solo aparecen al
correrlo de verdad:

1. Errores de sintaxis dentro de la expresión de un `CHECK`. SQLAlchemy pasa esas
   cadenas literalmente a PostgreSQL sin analizarlas.
2. La extensión `btree_gist`, que las dos `EXCLUDE` necesitan y que hay que crear
   **antes** de esas tablas.

Por eso el primer paso de tu revisión es correrlo en local, y por eso las 209
expresiones de `CHECK` son el punto que conviene mirar con más atención.

---

## Cómo revisarlo (30 minutos)

### 1. Coloca los archivos

Copia la carpeta `app/models/` completa y `app/extensions.py` sobre tu proyecto.
`extensions.py` sustituye el que tenías: ahora construye `db` con
`model_class=Base`, que es lo que permite que los modelos sean SQLAlchemy 2.x
puro.

```powershell
cd C:\ruta\a\densa_niebla
.venv\Scripts\activate
python verificar_entorno.py
```

### 2. Corre los tres verificadores

```powershell
python validar_modelos.py
python auditar_vs_erd.py
python prueba_relaciones.py
```

No hay nada que configurar: `ERD_Logico_Densa_Niebla_v1.md` viene dentro del
paquete y `auditar_vs_erd.py` lo busca solo. Si lo mueves de sitio, pásale la
ruta: `python auditar_vs_erd.py C:\ruta\a\ERD_Logico_Densa_Niebla_v1.md`.

### 3. Prueba el DDL contra tu PostgreSQL local, sin migraciones

Un solo comando. Crea una base **desechable**, corre el DDL, cuenta lo creado,
comprueba que las `EXCLUDE` bloqueen un solapamiento real, y borra la base
siempre, incluso si algo falla. No toca `densa_niebla_dev` ni Alembic.

```powershell
python probar_ddl_postgres.py
```

Toma la conexión de `DEV_DATABASE_URL` o `DATABASE_URL` (lee el `.env`). Si
prefieres indicarla a mano:

```powershell
python probar_ddl_postgres.py postgresql+psycopg://postgres:clave@localhost:5432/postgres
```

Debe terminar en `PRUEBA SUPERADA`, con 50 tablas y 2 `EXCLUDE`. Si PostgreSQL
rechaza algo, imprime la sentencia exacta que falló.

Si prefieres hacerlo a mano, `ddl_generado.sql` ya es ejecutable tal cual: trae
`CREATE EXTENSION btree_gist` de cabecera y va envuelto en una transacción con
`ON_ERROR_STOP`, así que o se crea todo o no se crea nada.

```powershell
psql -U postgres -c "CREATE DATABASE densa_ddl_test;"
psql -U postgres -d densa_ddl_test -f ddl_generado.sql
psql -U postgres -d densa_ddl_test -c "\dt"
psql -U postgres -c "DROP DATABASE densa_ddl_test;"
```

### 4. Lo que conviene mirar con ojo crítico

En este orden de importancia:

**a) Los métodos de costeo.** `products.costing_method` acepta `SPECIFIC_BATCH`,
`WEIGHTED_AVERAGE` y `SYSTEM_DEFAULT`. Revisa que el default global que
propusiste (`WEIGHTED_AVERAGE`) esté en `INITIAL_APP_SETTINGS` en `setting.py`, y
que `sale_items.costing_method_used` te sirva para auditar.

**b) Los 13 tipos de movimiento de inventario** en `MOVEMENT_TYPES` en
`inventory.py`. Es el catálogo del que depende todo el kardex. Si falta un caso
real de tu operación, es mucho más barato añadirlo ahora.

**c) Los estados.** Cada tupla en MAYÚSCULAS al comienzo de cada archivo es un
dominio cerrado que se convierte en un `CHECK`. Añadir un valor después es una
migración; ahora es una línea. Revisa sobre todo `SALE_STATUSES`,
`PURCHASE_STATUSES`, `PROCESS_EXECUTION_STATUSES` y `BATCH_STATUSES`.

**d) Las unidades.** `UNIT_DIMENSIONS` en `unit.py`. Aquí es donde entran los
factores de arroba, carga y saco que quedaron pendientes de confirmar con
administración. No están cargados: la tabla existe, los valores los defines tú.

**e) Los `ondelete`.** Busca `ondelete="CASCADE"` en todos los archivos y
confirma que solo aparece de cabecera a detalle del mismo documento. Cualquier
`CASCADE` fuera de ese patrón es un riesgo de pérdida de datos.

---

## Decisiones que tomé al escribir el código

El ERD dejaba varios puntos sin especificar. Estas son las decisiones y su
razón, para que las apruebes o las cambies.

**Los tipos de dato son alias, no declaraciones sueltas.** `base.py` define
`Money`, `Quantity`, `UnitPrice`, `Factor`, `Percent`, `TS`, `Day`, `Currency`.
Un modelo no puede equivocarse en la precisión porque no la escribe: la importa.
Si mañana el dinero necesita 4 decimales, se cambia en un solo lugar.

**Los enums son tuplas de módulo, no clases.** Cada archivo expone sus dominios
en MAYÚSCULAS (`SALE_STATUSES`, `MOVEMENT_TYPES`, …) y los aplica con el helper
`enum_check`. Los formularios y las plantillas los importan de ahí, así que la
lista de opciones de un `<select>` nunca puede divergir del `CHECK` de la base de
datos. Son 65 catálogos.

**Solo tres claves foráneas quedan diferidas.** Son los tres ciclos que el ERD
anticipó en la sección 17: `users.party_id` ↔ `parties`,
`parties.default_price_list_id` ↔ `price_lists`, y `batches.purchase_item_id` ↔
`purchase_items`. Llevan `use_alter=True`, que es lo que hace que Alembic las
emita como `ALTER TABLE` aparte en vez de atascarse. Al principio había 120
diferidas porque marqué todas las de auditoría; las quité al comprobar que
`users` se crea primero y no hay ciclo. La migración inicial queda mucho más
limpia de revisar.

**Las tablas append-only no llevan mixin.** `inventory_movements`,
`invoice_events` y `shipment_events` declaran sus columnas de tiempo a mano y no
tienen `updated_at`, porque tener una columna que dice cuándo se modificó un
registro que por definición no se modifica es una invitación a modificarlo.

**Las invariantes de varias tablas están documentadas, no implementadas.** La más
importante es la de `sale_item_batches`: la suma de las cantidades asignadas por
lote debe igualar la cantidad de la línea de venta. No se puede expresar como
`CHECK` porque una restricción de tabla no agrega filas de otra. Está en el
docstring con el prefijo `Invariante de servicio:` y hay una propiedad
`SaleItem.is_batch_allocation_balanced` que la evalúa; hacerla cumplir es
responsabilidad de `app/services/sales.py`. Lo mismo aplica a
`SUM(payment_allocations.amount) <= payments.amount`.

**Añadí `CHECK` de rango que el ERD no listaba.** Cantidades no negativas,
porcentajes entre 0 y 1, latitud y longitud en rango, `valid_to >= valid_from`,
un lote que no puede ser su propio padre, una categoría que no puede ser su
propio padre, un movimiento que no puede revertirse a sí mismo. Son baratos y
atrapan errores de captura. Si alguno te estorba, se quita.

**Las propiedades de dominio son de solo lectura.** `Sale.balance_due`,
`Sale.is_overdue`, `Payment.available_amount`, `Party.active_roles()`,
`Batch.parent_batches`, `AppSetting.typed_value`. Nada que escriba en la base de
datos ni que calcule costos: eso va en `services`, como manda el principio de
arquitectura.

**`app_settings.typed_value`** sí convierte el valor según `value_type`. Es
serialización, no lógica de negocio, y tenerla en el modelo evita que cada
consumidor repita el `Decimal(...)` o el `json.loads(...)`.

---

## Lo que sigue, en orden

1. **Tú revisas y apruebas** (o marcas ajustes).
2. **`app/services/costing.py` y `app/services/units.py`, con pruebas.** Son los
   dos de los que depende todo lo demás; el ERD dice explícitamente que van
   primero. `costing.py` implementa `resolve_outbound_cost(...)` con los dos
   métodos; `units.py` la conversión con búsqueda de camino.
3. **Recién entonces, las migraciones**, en las seis tandas de la sección 17 del
   ERD, empezando por `CREATE EXTENSION btree_gist`.
4. **El comando de siembra** `flask seed initial` con los datos maestros.
5. **La aplicación usable:** autenticación y CRUD de terceros y productos, antes
   de entrar a inventario y producción.

El paso 2 antes del 3 es deliberado. Escribir el costeo obliga a usar los modelos
de verdad, y ahí es donde aparecen los errores de diseño que una revisión de
código no encuentra. Es mucho mejor descubrirlos antes de que exista la primera
migración que después.
