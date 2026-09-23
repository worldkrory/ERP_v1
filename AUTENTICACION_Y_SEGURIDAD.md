# Sistema de Autenticación y Control de Acceso - ERP Densa Niebla

## 📋 Descripción General

Se ha implementado un sistema robusto de autenticación y autorización basado en roles, con control de integridad para la eliminación de ventas.

---

## 🔐 Módulo de Autenticación (`app/auth/`)

### Características principales:

#### 1. **Login/Logout Seguro**
- Validación de credenciales con contraseñas hasheadas
- Bloqueo automático tras 5 intentos fallidos (15 minutos)
- Registro de último login exitoso
- CSRF protection integrado
- Validación de URL segura para redirecciones

**Ruta**: `POST /auth/login` (también GET para formulario)
**Template**: `app/auth/templates/auth/login.html`

#### 2. **Gestión de Sesiones**
- Flask-Login integrado
- Sesión fuerte (session_protection="strong")
- Solo usuarios activos y no bloqueados
- Endpoint de verificación de sesión: `GET /api/v1/auth/session`

#### 3. **Decoradores de Autorización** (`app/auth/decorators.py`)

```python
# Requerir rol específico (cualquiera de los especificados)
@require_role("VENTAS", "ADMIN")
def mi_ruta():
    pass

# Requerir admin
@admin_only
def solo_admin():
    pass

# Registrar acción en auditoría
@audit_action("DELETE_SALE")
def mi_accion():
    pass
```

#### 4. **Códigos de Rol Disponibles**
- `ADMIN`: Acceso total al sistema
- `VENTAS`: Crear, editar y gestionar ventas
- `PRODUCCION`: Gestión de producción
- `INVENTARIO`: Control de inventario
- `CONTABILIDAD`: Movimientos financieros
- `CONSULTA`: Solo lectura

---

## 🗑️ Cancelación de Ventas (No Eliminación)

### Diseño: Mantener Historial Completo

En lugar de eliminar ventas, el sistema las **cancela**. Esto permite:

✅ **Auditoría completa**: Mantener registro de qué pasó
✅ **Devoluciones**: Crear devoluciones referenciando la venta original
✅ **Historial**: Consultar ventas canceladas para análisis
✅ **Integridad**: No romper referencias en otros módulos

### Funcionalidad: `cancel_sale()` en `app/services/sale_services.py`

La función implementa:

1. **Validaciones**:
   - Solo cancela DRAFT o CONFIRMED
   - Solo revierte inventario si está CONFIRMED
   - Registra razón de cancelación

2. **Efectos Secundarios**:
   - Revierte automáticamente movimientos de inventario
   - Notifica a Telegram del evento
   - Registra en logs quién canceló y por qué

3. **Uso**:
```python
from app.services.sale_services import cancel_sale

cancel_sale(
    session=db.session,
    sale=sale_object,
    reason="Solicitado por el cliente",
    created_by_id=user_id,
    notify_telegram=True,
    cancelled_by_name="juan@empresa.com"
)
```

### Notificación en Telegram

Cuando se cancela una venta, se envía automáticamente a Telegram:

```
⚠️ VENTA CANCELADA
Venta: V-2026-001
Cliente: Cafetería La Montaña
Total: COP 50,000.00
Estado anterior: CONFIRMED
Razón: Solicitado por el cliente
Cancelada por: juan@empresa.com
Timestamp: 2026-09-05 14:30:45
```

**Configuración requerida**:
- `TELEGRAM_BOT_TOKEN`: Token del bot
- `TELEGRAM_CHAT_ID`: ID del chat/grupo

---

## 🛣️ Rutas Protegidas de Ventas

Todas las rutas de API ahora requieren autenticación y rol apropiado:

### **Creación de Ventas**
```
POST /api/v1/sales
Roles requeridos: VENTAS, ADMIN
```

### **Agregar Items a Venta**
```
POST /api/v1/sales/<sale_id>/items
Roles requeridos: VENTAS, ADMIN
```

### **Listar Ventas**
```
GET /api/v1/sales
Roles requeridos: VENTAS, CONSULTA, ADMIN
```

### **Actualizar Venta**
```
PUT /api/v1/sales/<sale_id>
Roles requeridos: VENTAS, ADMIN
```

### **Eliminar/Cancelar Venta** ⚠️
```
DELETE /api/v1/sales/<sale_id>
Roles requeridos: ADMIN, VENTAS

Body (JSON):
{
    "reason": "Cancelado por solicitante"
}
```

**Respuesta exitosa (200)**:
```json
{
  "cancelled": true,
  "id": 123,
  "sale_number": "V-2026-001",
  "status_anterior": "CONFIRMED",
  "status_nuevo": "CANCELLED",
  "razón": "Cancelado por solicitante",
  "mensaje": "Venta V-2026-001 cancelada exitosamente. Puedes crear devoluciones referenciando esta venta."
}
```

**Error (409 Conflict)**:
```json
{
  "error": "Solo se puede cancelar una venta abierta o confirmada."
}
```

**Qué sucede**:
1. ✅ La venta cambia a estado CANCELLED
2. ✅ Se registra quién la canceló y por qué
3. ✅ Se revierten movimientos de inventario si estaba CONFIRMED
4. ✅ Se notifica a Telegram
5. ✅ Puedes crear devoluciones referenciando esta venta
6. ✅ Se mantiene completo el historial para auditoría

### **Panel Admin de Ventas**
```
GET /ventas
Roles requeridos: VENTAS, ADMIN
```

### **Subir Comprobante de Pago**
```
POST /api/v1/payments/<payment_id>/receipt
Roles requeridos: VENTAS, CONTABILIDAD, ADMIN
```

---

## 🚀 Flujo de Autenticación

### Para nuevos usuarios:

1. **Login inicial**
   - Navegar a `/auth/login`
   - Ingresar email y contraseña
   - Sistema valida y crea sesión

2. **Primer acceso al panel**
   - Automáticamente redirige a `/ventas` si tiene rol VENTAS/ADMIN
   - Si no, redirige a login

3. **Bloqueo de cuenta**
   - 5 intentos fallidos = bloqueo automático
   - Duración: 15 minutos (configurable)
   - Usuario puede reintentar después

### Logout
```
GET /auth/logout
```
Cierra sesión y redirige a login con mensaje de confirmación

---

## 🔍 Auditoría

Los siguientes eventos se registran automáticamente:

- ✅ Login exitoso (email, IP, timestamp)
- ❌ Intentos fallidos de login
- 🚫 Bloqueos de cuenta por intentos
- 🗑️ Cancelación de ventas (usuario, ID, número, razón)
- 📤 Subida de comprobantes de pago
- 🔔 Notificaciones enviadas a Telegram (timestamp, destinatarios)

**Ubicación**: Logs de aplicación (`logging.getLogger(__name__)`)

### Eventos en Telegram

Los siguientes eventos generan notificaciones automáticas a Telegram:

1. **Nueva Venta**: Información básica y monto
2. **Venta Cancelada**: Razón y usuario que canceló
3. **Comprobante Recibido**: Foto del comprobante con detalles

Ejemplo de evento:
```
⚠️ VENTA CANCELADA
Venta: V-2026-001
Cliente: Cafetería La Montaña
Total: COP 50,000.00
Estado anterior: CONFIRMED
Razón: Cliente solicita cancelación
Cancelada por: juan@empresa.com
Timestamp: 2026-09-05 14:30:45
```

---

## 💡 Notas de Desarrollo

### Agregar nuevos roles
1. Editar `ROLE_CODES` en `app/models/user.py`
2. Usar en decoradores:
```python
@require_role("MI_NUEVO_ROL")
def mi_ruta():
    pass
```

### Proteger nuevas rutas
```python
from flask_login import login_required
from app.auth.decorators import require_role, audit_action

@mi_blueprint.post("/endpoint")
@login_required
@require_role("ROL_REQUERIDO")
@audit_action("DESCRIPCION_ACCION")
def mi_endpoint():
    # Código protegido
    pass
```

### Testing de autenticación
```python
# En tests, usar client.post() con credenciales
# o usar Flask-Login testing utilities
```

---

## ⚙️ Configuración Recomendada

### En Producción (Heroku):
1. `FLASK_CONFIG=production` ✅ Ya implementado
2. Configurar `SECRET_KEY` segura en variables de entorno
3. Implementar rate limiting (nginx o fail2ban)
4. HTTPS obligatorio (`SESSION_COOKIE_SECURE=True`)
5. Monitoreo de intentos de login fallidos

### En Desarrollo:
```bash
# Crear usuario de prueba
python
>>> from app import create_app, db
>>> from app.models.user import User
>>> from werkzeug.security import generate_password_hash
>>> app = create_app("development")
>>> with app.app_context():
...     user = User(
...         email="test@example.com",
...         password_hash=generate_password_hash("password123"),
...         full_name="Usuario Prueba",
...         is_active=True
...     )
...     db.session.add(user)
...     db.session.commit()
```

---

## 📊 Resumen de Cambios

| Componente | Antes | Después |
|-----------|-------|---------|
| Rutas de Sales | Sin protección | ✅ Protegidas con auth + roles |
| Eliminación de Ventas | Eliminación directa | ✅ Validaciones de integridad |
| Login | Inexistente | ✅ Sistema seguro implementado |
| Auditoría | No | ✅ Registro automático de acciones |
| Bloqueo de Cuenta | No | ✅ Después de 5 intentos fallidos |

---

## 📝 Próximos Pasos (Sugeridos)

1. **Tabla de Auditoría**: Crear tabla `audit_logs` para persistir eventos
2. **Rate Limiting**: Implementar a nivel de infraestructura (nginx)
3. **2FA**: Agregar autenticación de dos factores
4. **Recuperación de Contraseña**: Implementar reset seguro
5. **Dashboard de Auditoría**: Panel para visualizar acciones
6. **Integración LDAP/OAuth**: Para empresas grandes

---

## 📞 Soporte

Para dudas sobre:
- **Autenticación**: Ver `app/auth/routes.py`
- **Autorización**: Ver `app/auth/decorators.py`
- **Eliminación de Ventas**: Ver `app/services/sale_services.py:delete_sale()`
- **Modelos**: Ver `app/models/user.py`

