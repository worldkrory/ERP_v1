from flask import Flask

from config import DevelopmentConfig
from app.extensions import db, migrate, login_manager


def create_app(config_class=DevelopmentConfig):
    
    app = Flask(__name__)

    app.config.from_object(config_class)

    db.init_app(app)
    migrate.init_app(app, db)
    login_manager.init_app(app)
    
    @app.route('/')
    def index():
        return "Densa Niebla ERP v.1 funcionando correctamente!"
    
    return app