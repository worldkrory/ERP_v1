"""Decoradores para control de acceso y autorización.

Proporciona:
- @login_required: Requerimiento de autenticación
- @require_role: Requerimiento de rol específico
- @require_any_role: Requerimiento de cualquier rol en una lista
- @audit_action: Auditoría de acciones sensibles
"""

from functools import wraps
from datetime import datetime, timezone

from flask import jsonify, render_template
from flask_login import current_user

from app.extensions import db
from app.models.user import User


def require_role(*roles):
    """Decorador que requiere que el usuario tenga uno o más roles específicos.
    
    Args:
        *roles: Códigos de rol requeridos (ej: "ADMIN", "VENTAS")
        
    Raises:
        403: Si el usuario no tiene ninguno de los roles requeridos
    """
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if not current_user.is_authenticated:
                return jsonify({"error": "Autenticación requerida"}), 401
            
            user_roles = current_user.role_codes
            if not any(role in user_roles for role in roles):
                return jsonify({
                    "error": f"Se requiere uno de los roles: {', '.join(roles)}"
                }), 403
                
            return f(*args, **kwargs)
        return decorated_function
    return decorator


def require_any_role(*roles):
    """Alias de require_role para claridad semántica."""
    return require_role(*roles)


def require_all_roles(*roles):
    """Decorador que requiere que el usuario tenga TODOS los roles especificados."""
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if not current_user.is_authenticated:
                return jsonify({"error": "Autenticación requerida"}), 401
            
            user_roles = current_user.role_codes
            if not all(role in user_roles for role in roles):
                return jsonify({
                    "error": f"Se requieren todos los roles: {', '.join(roles)}"
                }), 403
                
            return f(*args, **kwargs)
        return decorated_function
    return decorator


def audit_action(action_type: str):
    """Decorador que registra acciones sensibles con auditoría.
    
    Args:
        action_type: Tipo de acción (ej: "DELETE_SALE", "EDIT_USER")
    
    Registra:
        - Usuario que ejecutó la acción
        - Timestamp
        - Tipo de acción
        - Parámetros de la solicitud
    """
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            result = f(*args, **kwargs)
            
            # Registrar auditoría (implementar en auditar tabla si existe)
            if current_user.is_authenticated:
                try:
                    # Aquí iría el registro en tabla audit_logs si existe
                    # audit_log = AuditLog(
                    #     user_id=current_user.id,
                    #     action_type=action_type,
                    #     timestamp=datetime.now(timezone.utc),
                    #     details={"kwargs": kwargs}
                    # )
                    # db.session.add(audit_log)
                    # db.session.commit()
                    pass
                except Exception as e:
                    # No fallar la acción por fallo de auditoría
                    print(f"Error registrando auditoría: {e}")
            
            return result
        return decorated_function
    return decorator


def admin_only(f):
    """Decorador que requiere que el usuario sea superusuario (admin)."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated:
            return jsonify({"error": "Autenticación requerida"}), 401
        
        if not current_user.is_superuser:
            return jsonify({"error": "Se requieren permisos de administrador"}), 403
            
        return f(*args, **kwargs)
    return decorated_function
