"""
EJEMPLOS DE USO: Sistema de Autenticación y Eliminación de Ventas

Este archivo contiene ejemplos prácticos de cómo usar las nuevas
características implementadas en el ERP.
"""

# ============================================================================
# EJEMPLO 1: Proteger una ruta con autenticación y roles
# ============================================================================

from flask import Blueprint, jsonify
from flask_login import login_required, current_user
from app.auth.decorators import require_role, admin_only, audit_action

mi_blueprint = Blueprint("mi_modulo", __name__, url_prefix="/api/v1")


@mi_blueprint.post("/recursos")
@login_required
@require_role("ADMIN", "VENDEDOR")
@audit_action("CREAR_RECURSO")
def crear_recurso():
    """
    Crear un recurso.
    
    Restricciones:
    - Usuario debe estar autenticado
    - Usuario debe tener rol ADMIN o VENDEDOR
    - La acción se registra en auditoría
    """
    print(f"Usuario actual: {current_user.email}")
    print(f"Roles del usuario: {current_user.role_codes}")
    return jsonify({"status": "ok", "usuario": current_user.email}), 201


@mi_blueprint.get("/admin-panel")
@admin_only
def panel_admin():
    """Solo usuarios superadmin pueden acceder."""
    return jsonify({
        "panel": "Administración",
        "admin": current_user.is_superuser
    })


# ============================================================================
# EJEMPLO 2: Usar decoradores personalizados
# ============================================================================

from app.auth.decorators import require_all_roles


@mi_blueprint.post("/accion-critica")
@login_required
@require_all_roles("ADMIN", "AUDITOR")
def accion_critica():
    """
    Esta acción requiere TODOS los roles: ADMIN Y AUDITOR.
    (A diferencia de require_role que requiere solo uno)
    """
    return jsonify({"resultado": "Acción crítica ejecutada"})


# ============================================================================
# EJEMPLO 3: Eliminar una venta de forma robusta
# ============================================================================

from app.services.sale_services import delete_sale, SaleError
from app.models.sale import Sale
from app.extensions import db


def eliminar_venta_ejemplo(sale_id: int, user_id: int):
    """
    Ejemplo de cómo eliminar una venta de forma segura.
    
    Características:
    - Valida que sea DRAFT o CANCELLED
    - Verifica que no haya pagos
    - Revierte inventario automáticamente
    - Registra en auditoría
    """
    try:
        sale = db.session.get(Sale, sale_id)
        if not sale:
            raise ValueError("Venta no encontrada")
        
        # Llamar delete_sale que hace todas las validaciones
        delete_sale(
            db.session,
            sale,
            created_by_id=user_id
        )
        
        # Confirmar cambios
        db.session.commit()
        
        return {
            "exito": True,
            "mensaje": f"Venta {sale.sale_number} eliminada",
            "id": sale.id
        }
        
    except SaleError as e:
        # Error de lógica de negocio
        db.session.rollback()
        return {
            "exito": False,
            "error": str(e),
            "tipo": "RESTRICCION_INTEGRIDAD"
        }
    
    except Exception as e:
        # Error inesperado
        db.session.rollback()
        return {
            "exito": False,
            "error": str(e),
            "tipo": "ERROR_INTERNO"
        }


# ============================================================================
# EJEMPLO 4: Endpoint REST para eliminar ventas
# ============================================================================

@mi_blueprint.delete("/ventas/<int:venta_id>")
@login_required
@require_role("ADMIN", "VENTAS")
@audit_action("CANCEL_SALE")
def cancelar_venta_endpoint(venta_id: int):
    """
    Endpoint para cancelar una venta a través de REST API.
    
    Request:
        DELETE /api/v1/ventas/123
        Content-Type: application/json
        {
            "reason": "Cliente solicita cancelación"
        }
    
    Response (200 OK):
        {
            "cancelled": true,
            "id": 123,
            "sale_number": "V-2026-001",
            "status_anterior": "CONFIRMED",
            "status_nuevo": "CANCELLED",
            "razón": "Cliente solicita cancelación",
            "mensaje": "Venta cancelada exitosamente. Puedes crear devoluciones..."
        }
        
        Y automáticamente se envía a Telegram:
        ⚠️ VENTA CANCELADA
        Venta: V-2026-001
        Cliente: Cafetería La Montaña
        Total: COP 50,000.00
        Estado anterior: CONFIRMED
        Razón: Cliente solicita cancelación
        Cancelada por: juan@empresa.com
        Timestamp: 2026-09-05 14:30:45
    
    Response (409 Conflict):
        {
            "error": "Solo se puede cancelar una venta abierta o confirmada."
        }
    """
    sale = db.session.get(Sale, venta_id)
    if not sale:
        return jsonify({"error": "Venta no encontrada"}), 404
    
    payload = request.get_json(silent=True) or {}
    reason = payload.get("reason", "Cancelado sin razón especificada")
    
    try:
        cancel_sale(
            db.session,
            sale,
            reason=reason,
            created_by_id=current_user.id,
            notify_telegram=True,
            cancelled_by_name=current_user.email
        )
        db.session.commit()
        
        return jsonify({
            "cancelled": True,
            "id": venta_id,
            "sale_number": sale.sale_number,
            "status_anterior": "...",  # Capturado antes
            "status_nuevo": "CANCELLED",
            "razón": reason,
            "mensaje": "Venta cancelada. Puedes crear devoluciones referenciando esta venta."
        }), 200
        
    except SaleError as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 409
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": "Error al cancelar"}), 500


# ============================================================================
# EJEMPLO 5: Cancelar una venta en lugar de eliminarla
# ============================================================================

from app.services.sale_services import cancel_sale, SaleError


async def cancelar_venta_js():
    """
    JAVASCRIPT (Frontend) - Cancelar venta con razón:
    """
    code = """
    // Cancelar una venta
    async function cancelarVenta(ventaId) {
        const razon = prompt('Razón de cancelación:');
        
        if (!razon) {
            alert('Debes ingresar una razón');
            return;
        }
        
        const response = await fetch(`/api/v1/ventas/${ventaId}`, {
            method: 'DELETE',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ reason: razon })
        });
        
        if (response.ok) {
            const data = await response.json();
            alert(data.mensaje); 
            // "Venta cancelada. Puedes crear devoluciones referenciando esta venta."
            
            // Actualizar estado en UI
            document.getElementById(`venta-${ventaId}-status`).textContent = 'CANCELLED';
            document.getElementById(`venta-${ventaId}-reason`).textContent = data.razón;
            
            // El equipo en Telegram ya fue notificado automáticamente
            console.log('Notificación enviada a Telegram');
        } else {
            const error = await response.json();
            alert('Error: ' + error.error);
        }
    }
    
    // Ejecutar al hacer clic en botón "Cancelar"
    document.getElementById('btn-cancelar').addEventListener('click', () => {
        cancelarVenta(123);
    });
    """
    print(code)


# ============================================================================
# EJEMPLO 5b: Verificar sesión y permisos antes de cancelar
# ============================================================================


# ============================================================================
# EJEMPLO 6: Cancelar venta desde Python (CLI)
# ============================================================================

"""
PYTHON (CLI / Backend Task):

from app import create_app, db
from app.models.sale import Sale
from app.services.sale_services import cancel_sale

app = create_app("development")

with app.app_context():
    # Obtener venta a cancelar
    venta = Sale.query.filter_by(sale_number="V-2026-001").first()
    
    if not venta:
        print("Venta no encontrada")
    else:
        # Cancelar con notificación a Telegram
        cancel_sale(
            db.session,
            venta,
            reason="Cliente solicita devolución por defecto",
            created_by_id=1,  # Admin
            notify_telegram=True,
            cancelled_by_name="juan@empresa.com"
        )
        db.session.commit()
        
        print(f"✓ Venta {venta.sale_number} cancelada")
        print(f"  Razón: {venta.cancellation_reason}")
        print(f"  Timestamp: {venta.cancelled_at}")
        print("✓ Notificación enviada a Telegram")
        
        # Ahora puedo crear una devolución referenciando esta venta
        from app.services.sale_services import create_sale
        
        devolucion = create_sale(
            db.session,
            sale_number="DEV-2026-001",  # Número de devolución
            party_id=venta.party_id,
            channel=venta.channel,
            # reference_sale_id=venta.id  # Para futuras referencias
        )
        
        print(f"✓ Devolución creada: {devolucion.sale_number}")
        print(f"  Referencia: {venta.sale_number}")
"""


# ============================================================================
# EJEMPLO 7: Crear usuario con roles
# ============================================================================


# ============================================================================
# EJEMPLO 8: Manejo de excepciones de cancelación de ventas
# ============================================================================

from app.services.sale_services import cancel_sale, SaleError


def cancelar_venta_con_manejo_errores(venta_id: int, razon: str) -> dict:
    """
    Ejemplo de cómo manejar errores al cancelar una venta.
    
    Errores posibles:
    1. Solo DRAFT o CONFIRMED: "Solo se puede cancelar una venta abierta o confirmada."
    2. Telegram no disponible: Se registra en logs pero no falla
    3. Error en reversión de inventario: Se captura con detalles
    """
    try:
        venta = db.session.get(Sale, venta_id)
        if not venta:
            return {
                "exito": False,
                "error": "Venta no encontrada",
                "codigo": "NOT_FOUND"
            }
        
        # Cancelar con Telegram
        cancel_sale(
            db.session,
            venta,
            reason=razon,
            created_by_id=current_user.id,
            notify_telegram=True,
            cancelled_by_name=current_user.email
        )
        
        db.session.commit()
        
        return {
            "exito": True,
            "venta_id": venta.id,
            "numero": venta.sale_number,
            "status": "CANCELLED",
            "razón": razon,
            "timestamp": venta.cancelled_at.isoformat()
        }
        
    except SaleError as e:
        # Error de lógica de negocio
        db.session.rollback()
        return {
            "exito": False,
            "error": str(e),
            "codigo": "RESTRICCION_NEGOCIO",
            "sugerencia": "Verifica que la venta esté en DRAFT o CONFIRMED"
        }
    
    except Exception as e:
        # Error inesperado
        db.session.rollback()
        return {
            "exito": False,
            "error": "Error interno del servidor",
            "codigo": "ERROR_INTERNO",
            "detalles": str(e)
        }


# Usar:
resultado = cancelar_venta_con_manejo_errores(123, "Cliente solicita cancelación")
if resultado["exito"]:
    print(f"✓ Venta {resultado['numero']} cancelada")
else:
    print(f"✗ Error: {resultado['error']}")


# ============================================================================
# EJEMPLO 9: Manejo automático de bloqueo de usuarios
# ============================================================================

"""
El sistema implementa automáticamente:

1. Contador de intentos fallidos (failed_login_count)
2. Bloqueo tras 5 intentos (locked_until timestamp)
3. Duración del bloqueo: 15 minutos

Los intentos fallidos se registran automáticamente en:
- Logs de aplicación
- Campo last_login_at actualizado en login exitoso

Para desbloquear manualmente un usuario:
    user = User.query.filter_by(email="usuario@test.com").first()
    user.failed_login_count = 0
    user.locked_until = None
    db.session.commit()
"""


# ============================================================================
# EJEMPLO 9: Cascada de eliminación con integridad
# ============================================================================

"""
Cuando se cancela una venta:

1. CANCEL_SALE valida:
   ✓ Estado == DRAFT o CONFIRMED
   ✓ Usuario tiene rol VENTAS o ADMIN
   
2. Revierte automáticamente:
   ✓ Movimientos de inventario (si CONFIRMED)
   ✓ Asignaciones de lotes (batch_allocations)
   
3. Actualiza BD:
   ✓ UPDATE sales SET status='CANCELLED', cancelled_at=NOW() WHERE id=X
   ✓ Mantiene SaleItems (no cascada)
   ✓ Mantiene referencias de pagos (para auditoría)
   
4. Notificaciones:
   ✓ Telegram: Mensaje detallado
   ✓ Logs: Auditoría completa
   ✓ BD: Historial persistente
   
5. Permite:
   ✓ Crear devoluciones referenciando la venta
   ✓ Consultar histórico completo
   ✓ Auditar cambios
"""


# ============================================================================
# EJEMPLO 10: Testear cancelación de ventas
# ============================================================================

"""
PYTEST:

from flask import url_for

def test_ruta_protegida_sin_auth(client):
    '''Cliente sin autenticación debe ser redirigido'''
    response = client.get('/api/v1/datos-sensibles')
    assert response.status_code == 401

def test_ruta_protegida_sin_rol(client, usuario_sin_rol):
    '''Usuario sin rol correcto debe recibir 403'''
    client.force_login(usuario_sin_rol)
    response = client.get('/api/v1/datos-sensibles')
    assert response.status_code == 403

def test_cancelar_venta_draft(client, usuario_ventas, venta_draft):
    '''Usuario VENTAS puede cancelar venta DRAFT'''
    client.force_login(usuario_ventas)
    response = client.delete(
        f'/api/v1/ventas/{venta_draft.id}',
        json={"reason": "Cancelado por prueba"}
    )
    assert response.status_code == 200
    assert response.json["cancelled"] == True
    assert response.json["status_nuevo"] == "CANCELLED"

def test_cancelar_venta_confirmada(client, usuario_ventas, venta_confirmada):
    '''Usuario VENTAS puede cancelar venta CONFIRMED'''
    client.force_login(usuario_ventas)
    response = client.delete(
        f'/api/v1/ventas/{venta_confirmada.id}',
        json={"reason": "Cliente solicita"}
    )
    assert response.status_code == 200
    assert response.json["cancelled"] == True

def test_no_puede_cancelar_delivered(client, usuario_ventas, venta_delivered):
    '''No se puede cancelar venta DELIVERED'''
    client.force_login(usuario_ventas)
    response = client.delete(
        f'/api/v1/ventas/{venta_delivered.id}',
        json={"reason": "Intento de cancelación"}
    )
    assert response.status_code == 409
    assert "abierta o confirmada" in response.json["error"]
"""


if __name__ == "__main__":
    print(__doc__)
