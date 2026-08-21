from flask import Flask, render_template

from config import DevelopmentConfig
from app.extensions import db, migrate, login_manager


def create_app(config_class=DevelopmentConfig):
    
    app = Flask(__name__)

    app.config.from_object(config_class)

    db.init_app(app)
    migrate.init_app(app, db)
    login_manager.init_app(app)

    @login_manager.user_loader
    def load_user(user_id):
        return User.query.get(int(user_id))
    
    @app.route('/')
    def index():
        return "Densa Niebla ERP v.1 funcionando correctamente!"

    @app.route('/microlote/bourbon-rosado')
    def bourbon_rosado():
        return render_template('microlote_bourbon_rosado.html')

    
    
    return app