"""Rutas de autenticación: login, logout, gestión de sesiones."""

import logging
from datetime import datetime, timezone

from flask import Blueprint, render_template, redirect, url_for, flash, request, jsonify
from flask_login import login_user, logout_user, current_user
from werkzeug.security import check_password_hash

from app.extensions import db
from app.auth import auth_bp
from app.auth.forms import LoginForm
from app.models.user import User

from app.sales import sales_admin_bp, sales_bp

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
    """Login con validación de credenciales y control de cuenta activa."""

    next_page = (
        request.form.get("next")
        or request.args.get("next")
    )

    destination = "/ventas"

    if next_page and _is_safe_url(next_page):
        destination = next_page

    # Solo redirigir inmediatamente si ya existe una sesión.
    if current_user.is_authenticated:
        return redirect(destination)

    form = LoginForm()

    if form.validate_on_submit():
        email = form.email.data.strip().lower()

        user = db.session.scalar(
            db.select(User).where(User.email == email)
        )

        if user is None or not check_password_hash(
            user.password_hash,
            form.password.data,
        ):
            if user is not None:
                user.failed_login_count = (
                    user.failed_login_count or 0
                ) + 1

                if user.failed_login_count >= 5:
                    user.locked_until = datetime.now(timezone.utc)
                    db.session.commit()

                    logger.warning(
                        f"Cuenta {user.email} bloqueada por intentos fallidos",
                        extra={"user_id": user.id},
                    )

                    flash(
                        "Tu cuenta está bloqueada por demasiados "
                        "intentos fallidos.",
                        "danger",
                    )

                    return redirect(
                        url_for("auth.login", next=next_page)
                    )

                db.session.commit()

            flash("Correo o contraseña incorrectos.", "danger")

            logger.info(
                f"Intento de login fallido para {email}",
                extra={"ip": request.remote_addr},
            )

            return redirect(
                url_for("auth.login", next=next_page)
            )

        if not user.is_active:
            flash(
                "Tu cuenta está desactivada. Contacta al administrador.",
                "danger",
            )

            return redirect(
                url_for("auth.login", next=next_page)
            )

        user.failed_login_count = 0
        user.last_login_at = datetime.now(timezone.utc)
        db.session.commit()

        login_user(
            user,
            remember=request.form.get("remember") == "1",
        )

        logger.info(
            f"Login exitoso para usuario {user.email}",
            extra={
                "user_id": user.id,
                "ip": request.remote_addr,
            },
        )

        # Redirigir solo después de autenticar correctamente.
        return redirect(destination)

    # GET inicial o formulario con errores de validación.
    return render_template("auth/login.html", form=form)



@auth_bp.route("/login/google")
def google_login():
    """
    Envía al usuario a Google para autenticación OAuth/OpenID Connect.
    """
    redirect_uri = url_for("auth.google_callback", _external=True)

    return oauth.google.authorize_redirect(redirect_uri)


@auth_bp.route("/login/google/callback")
def google_callback():
    """
    Recibe el retorno de Google y permite entrar únicamente
    a usuarios previamente autorizados dentro del ERP.
    """
    try:
        token = oauth.google.authorize_access_token()
        user_info = token.get("userinfo")

        if not user_info:
            user_info = oauth.google.parse_id_token(token)

    except Exception:
        current_app.logger.exception("Error en autenticación con Google")
        flash("No fue posible validar tu cuenta de Google. Intenta nuevamente.", "danger")
        return redirect(url_for("auth.login"))

    google_sub = user_info.get("sub")
    email = (user_info.get("email") or "").strip().lower()
    email_verified = user_info.get("email_verified", False)

    if not google_sub or not email or not email_verified:
        flash("Google no confirmó una cuenta de correo válida.", "danger")
        return redirect(url_for("auth.login"))

    # Busca primero por Google ID y luego por correo institucional existente.
    user = User.query.filter(
        (User.google_sub == google_sub) | (User.email == email)
    ).first()

    # No crear usuarios automáticamente: solo personal previamente autorizado.
    if not user or not user.is_active:
        current_app.logger.warning(
            "Acceso Google no autorizado para el correo: %s",
            email
        )
        flash("Tu cuenta no está autorizada para ingresar al ERP.", "danger")
        return redirect(url_for("auth.login"))

    # Primera vinculación segura entre usuario existente y Google.
    if not user.google_sub:
        user.google_sub = google_sub
        db.session.commit()

    login_user(user, remember=True)

    flash(f"Bienvenido, {user.name or user.email}.", "success")
    return redirect(url_for("dashboard.index"))

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
