import os
from dotenv import load_dotenv

load_dotenv()

def get_database_url():

    url = os.getenv('DATABASE_URL')

    if not url:
        raise ValueError("DATABASE_URL variable de entorno no está configurada. Por favor, asegúrate de que esté presente en el archivo .env o en las variables de entorno del sistema.")
    
    if url.startswith("postgres://"):
        url = url.replace(
            "postgres://",
            "postgresql+psycopg://",
            1
        )

    elif url.startswith("postresql://"):
        url = url.replace(
            "postgresql://",
            "postgresql+psycopg://",
            1
        )
    return url

class Config:
    SECRET_KEY = os.getenv('SECRET_KEY')

    SQLALCHEMY_DATABASE_URI = get_database_url()

    SQLALCHEMY_TRACK_MODIFICATIONS = False


class DevelopmentConfig(Config):
    DEBUG = True
    

class ProductionConfig(Config):
    DEBUG = False


class TestingConfig(Config):
    TESTING = True