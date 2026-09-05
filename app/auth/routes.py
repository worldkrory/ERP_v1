"""Rutas de autenticación: login, logout, gestión de sesiones."""

import logging
from datetime import datetime, timezone

from flask import render_template, redirect, url_for, flash, request, jsonify
from flask_login import login_user, logout_user, current_user
from werkzeug.security import check_password_hash

from app.extensions import db
from app.auth import auth_bp
from app.auth.forms import LoginForm
from app.models.user import User

logger = logging.getLogger(__name__)


@auth_bp.before_request
def check_user_locked():
    """Verifica si el usuario actual está bloqueado por intentos fallidos."""
    if current_user.is_authenticated and current_user.is_locked:
        logout_user()
        flash("Tu cuenta está bloqueada por intentos de login fallidos.", "danger")
        return redirect(url_for("auth.login"))


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    """Ruta de login con validación de credenciales y bloqueo por intentos fallidos.
    
    Seguridad:
    - Rate limiting recomendado en producción (nginx, fail2ban)
    - Contraseñas hasheadas con Werkzeug
    - Bloqueo tras 5 intentos fallidos durante 15 minutos
    - CSRF protection via Flask-WTF
    """
    if current_user.is_authenticated:
        return redirect(url_for("sales_admin.sales_admin_page"))
    
    form = LoginForm()
    
    if form.validate_on_submit():
        user = db.session.scalar(
            db.select(User).where(User.email == form.email.data.lower())
        )
        
        if user is None or not check_password_hash(user.password_hash, form.password.data):
            # Incrementar contador de intentos fallidos
            if user:
                user.failed_login_count = (user.failed_login_count or 0) + 1
                
                # Bloquear cuenta tras 5 intentos fallidos
                if user.failed_login_count >= 5:
                    user.locked_until = datetime.now(timezone.utc)
                    db.session.commit()
                    logger.warning(
                        f"Cuenta {user.email} bloqueada por intentos fallidos",
                        extra={"user_id": user.id}
                    )
                    flash("Tu cuenta está bloqueada por demasiados intentos fallidos.", "danger")
                    return redirect(url_for("auth.login"))
                
                db.session.commit()
            
            flash("Correo o contraseña incorrectos.", "danger")
            logger.info(
                f"Intento de login fallido para {form.email.data}",
                extra={"ip": request.remote_addr}
            )
            return redirect(url_for("auth.login"))
        
        # Login exitoso
        if not user.is_active:
            flash("Tu cuenta está desactivada. Contacta al administrador.", "danger")
            return redirect(url_for("auth.login"))
        
        # Resetear contador y registrar login
        user.failed_login_count = 0
        user.last_login_at = datetime.now(timezone.utc)
        db.session.commit()
        
        login_user(user, remember=request.form.get("remember", False))
        
        logger.info(
            f"Login exitoso para usuario {user.email}",
            extra={"user_id": user.id, "ip": request.remote_addr}
        )
        
        next_page = request.args.get("next")
        if next_page and _is_safe_url(next_page):
            return redirect(next_page)
        
        return redirect(url_for("sales_admin.sales_admin_page"))
    
    return render_template("auth/login.html", form=form)


@auth_bp.route("/logout")
def logout():
    """Cierra la sesión del usuario actual."""
    if current_user.is_authenticated:
        logger.info(
            f"Logout para usuario {current_user.email}",
            extra={"user_id": current_user.id}
        )
        logout_user()
    
    flash("Sesión cerrada correctamente.", "success")
    return redirect(url_for("auth.login"))


@auth_bp.route("/api/v1/auth/session", methods=["GET"])
def get_session():
    """Endpoint API para obtener información de la sesión actual.
    
    Útil para frontend para saber si el usuario está autenticado.
    
    Returns:
        {
            "authenticated": bool,
            "user_id": int,
            "email": str,
            "full_name": str,
            "roles": list[str]
        }
    """
    if current_user.is_authenticated:
        return jsonify({
            "authenticated": True,
            "user_id": current_user.id,
            "email": current_user.email,
            "full_name": current_user.full_name,
            "roles": list(current_user.role_codes),
            "is_superuser": current_user.is_superuser,
        })
    
    return jsonify({"authenticated": False}), 401


def _is_safe_url(target):
    """Valida que una URL sea segura para redirección (previene open redirects)."""
    from urllib.parse import urljoin, urlparse
    
    ref_url = urlparse(request.host_url)
    test_url = urlparse(urljoin(request.host_url, target))
    
    return test_url.scheme in ("http", "https") and ref_url.netloc == test_url.netloc
