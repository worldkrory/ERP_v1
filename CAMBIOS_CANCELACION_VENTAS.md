# Actualización: Cancelación de Ventas con Notificación en Telegram

## 🎯 Cambios Realizados

### 1. **Eliminación → Cancelación**
- ❌ REMOVIDO: Eliminación física de ventas
- ✅ IMPLEMENTADO: Cancelación lógica (cambio de estado CANCELLED)

**Beneficios**:
- 📋 Historial completo y auditable
- 🔄 Permite devoluciones referenciando la venta
- 💾 No rompe integridad referencial
- 📊 Mejor análisis histórico

### 2. **Notificación en Telegram**
- ✅ IMPLEMENTADO: `notify_sale_cancelled()` en `app/services/telegram_service.py`
- Notificación automática cuando se cancela una venta
- Incluye: razón, usuario que canceló, timestamp

### 3. **Mejoras en `cancel_sale()`**
```python
# ANTES (básico)
cancel_sale(session, sale, reason="Cancelado")

# AHORA (completo)
cancel_sale(
    session,
    sale,
    reason="Cliente solicita devolución",
    created_by_id=user_id,
    notify_telegram=True,
    cancelled_by_name="juan@empresa.com"
)
```

### 4. **Endpoint DELETE Mejorado**
```
DELETE /api/v1/sales/123
Body: {"reason": "Cliente solicita cancelación"}

Response:
{
  "cancelled": true,
  "id": 123,
  "sale_number": "V-2026-001",
  "status_anterior": "CONFIRMED",
  "status_nuevo": "CANCELLED",
  "razón": "Cliente solicita cancelación",
  "mensaje": "Venta cancelada. Puedes crear devoluciones referenciando esta venta."
}
```

---

## 📁 Archivos Modificados

1. **`app/services/telegram_service.py`**
   - ✅ Agregada función `notify_sale_cancelled()`

2. **`app/services/sale_services.py`**
   - ✅ Mejorada `cancel_sale()` con Telegram
   - ✅ Deprecada `delete_sale()` (ahora cancela)

3. **`app/sales/routes.py`**
   - ✅ Cambio: DELETE → cancel_sale() + notificación
   - ✅ Endpoint actualizado con nuevo payload

4. **`AUTENTICACION_Y_SEGURIDAD.md`**
   - ✅ Actualizada documentación

---

## 🚀 Flujo de Cancelación

```
Usuario solicita: DELETE /api/v1/sales/123

    ↓

Sistema valida:
  ✓ ¿Venta existe?
  ✓ ¿Rol VENTAS o ADMIN?
  ✓ ¿Estado es DRAFT o CONFIRMED?

    ↓

Sistema cancela:
  → Cambia estado a CANCELLED
  → Revierte inventario si CONFIRMED
  → Registra razón y usuario

    ↓

Sistema notifica:
  → Telegram: Mensaje de cancelación
  → Logs: Auditoría completa
  → BD: Historial persistente

    ↓

Respuesta: 200 OK + detalles de cancelación
```

---

## 📢 Notificación Telegram

### Formato del Mensaje

```
⚠️ VENTA CANCELADA
Venta: V-2026-001
Cliente: Cafetería La Montaña
Total: COP 50,000.00
Estado anterior: CONFIRMED
Razón: Cliente solicita devolución
Cancelada por: juan@empresa.com
Timestamp: 2026-09-05 14:30:45
```

### Configuración Requerida

En variables de entorno o config:
```python
TELEGRAM_BOT_TOKEN = "123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11"
TELEGRAM_CHAT_ID = "-1001234567890"
```

---

## ✅ Casos de Uso

### Caso 1: Cliente solicita cancelación
```bash
curl -X DELETE http://localhost:5000/api/v1/sales/123 \
  -H "Content-Type: application/json" \
  -d '{"reason": "Cliente solicita cancelación por cambio de planes"}'
```

**Resultado**:
- Venta pasa a CANCELLED
- Inventario revertido
- Telegram notifica
- Devolución puede referenciarse

### Caso 2: Error en venta
```bash
curl -X DELETE http://localhost:5000/api/v1/sales/456 \
  -H "Content-Type: application/json" \
  -d '{"reason": "Error en facturación, generaremos nueva venta"}'
```

### Caso 3: Sistema automático
```python
from app.services.sale_services import cancel_sale

cancel_sale(
    db.session,
    problematic_sale,
    reason="Venta duplicada detectada por sistema",
    created_by_id=1,
    notify_telegram=True,
    cancelled_by_name="Sistema Automático"
)
db.session.commit()
```

---

## 🔄 Devoluciones (Próximo Paso)

Con este sistema ya puedes:

1. Crear venta X
2. Cancelar venta X (si es necesario)
3. **Crear devolución** referenciando venta X cancelada
4. Historial completo: venta → cancelación → devolución

Ejemplo:
```python
# Crear devolución referenciando venta cancelada
return_sale = create_sale(
    db.session,
    sale_number="DEV-2026-001",  # Número de devolución
    party_id=original_sale.party_id,
    channel=original_sale.channel,
    reference_sale_id=original_sale.id,  # Referencia
)
# Agregar items con cantidades negativas
# Confirmar devolución
# Sistema valida que original fue cancelada
```

---

## ⚠️ Cambios Importantes

| Concepto | Antes | Ahora |
|----------|-------|-------|
| Acción | Eliminación física | Cancelación lógica |
| Estado | Removida de BD | CANCELLED |
| Historial | Perdido | Completo |
| Auditoría | No | Sí |
| Devoluciones | No referenciable | Referenciable |
| Telegram | No | Automático |
| Rollback | No posible | Completo |

---

## 🧪 Testing

```python
# Test: Cancelar venta CONFIRMED
def test_cancel_confirmed_sale():
    sale = create_sale(...)
    sale.status = "CONFIRMED"
    
    cancel_sale(db.session, sale, reason="Test")
    
    assert sale.status == "CANCELLED"
    assert sale.cancellation_reason == "Test"
    # Telegram debería haber sido notificado

# Test: No permitir cancelar DELIVERED
def test_cannot_cancel_delivered():
    sale = create_sale(...)
    sale.status = "DELIVERED"
    
    with pytest.raises(SaleError):
        cancel_sale(db.session, sale, reason="Test")
```

---

## 📌 Resumen

✅ **Antes**: Eliminación directa (perdía datos, rompía integridad)

✅ **Ahora**: Cancelación ordenada (auditable, históricamente completa, Telegram)

✅ **Beneficio**: Mejor control y análisis del ciclo de vida de ventas

✅ **Próximo**: Implementar devoluciones referenciando ventas canceladas
