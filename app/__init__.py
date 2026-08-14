from flask import Flask

def create_app():
    app = Flask(__name__)
    
    @app.route('/')
    def index():
        return "Densa Niebla ERP v.1 funcionando correctamente!"
    
    return app