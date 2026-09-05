from flask import Flask, jsonify, render_template, redirect, url_for
import os
from config import config_by_name
from app.extensions import db, migrate, login_manager
from app.parties import parties_admin_bp, parties_bp
from app.sales import sales_admin_bp, sales_bp
from app.auth import auth_bp

from app import models



def create_app(config_name=None):

    config_name = config_name or os.getenv("FLASK_CONFIG", "development")

    if config_name not in config_by_name:
        raise RuntimeError(
            f"FLASK_CONFIG='{config_name}' no es valido. "
            f"Opciones: {', '.join(config_by_name)}"
        )

    config_class = config_by_name[config_name]

    app = Flask(__name__)
    app.config.from_object(config_class)
    config_class.init_app(app)

    db.init_app(app)
    
    migrate.init_app(app, db, compare_type=True)
    login_manager.init_app(app)

    from app import models  # noqa: F401

    register_blueprints(app)

    @app.get("/health")
    def health():
        """Endpoint de verificación: confirma entorno y conexión a la base."""
        try:
            db.session.execute(db.text("SELECT 1"))
            database = "ok"
        except Exception:  # pragma: no cover
            database = "error"
        return jsonify(status="ok", env=config_name, database=database)
    
    @app.route('/')
    def index():
        """Ruta principal: redirige a login o al dashboard."""
        from flask_login import current_user
        
        if current_user.is_authenticated:
            return redirect(url_for("sales_admin.sales_admin_page"))
        return redirect(url_for("auth.login"))

    @app.route('/microlote/bourbon-rosado')
    def bourbon_rosado():
        return render_template('microlote_bourbon_rosado.html')

    
    
    return app

def register_blueprints(app):
    """Registro centralizado de blueprints por dominio.

    Se irán activando conforme se construya cada módulo:
    auth, dashboard, parties, products, sales, inventory,
    production, finance, expenses, invoices.
    """
    app.register_blueprint(auth_bp)
    app.register_blueprint(sales_bp)
    app.register_blueprint(sales_admin_bp)
    app.register_blueprint(parties_bp)
    app.register_blueprint(parties_admin_bp)
    return app