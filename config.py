
import os

from dotenv import load_dotenv

load_dotenv()

PSYCOPG_DIALECT = "postgresql+psycopg://"


def normalize_database_url(url):
    
    if url.startswith("postgres://"):
        return url.replace("postgres://", PSYCOPG_DIALECT, 1)
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", PSYCOPG_DIALECT, 1)
    return url


def get_database_url(*var_names):
    
    for name in var_names:
        url = os.getenv(name)
        if url:
            return normalize_database_url(url)
    raise RuntimeError(
        "No hay base de datos configurada. Variables consultadas: "
        + ", ".join(var_names)
    )


class Config:
    
    DATABASE_URL_VARS = ("DATABASE_URL",)

    SECRET_KEY = os.getenv("SECRET_KEY")
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    MAX_CONTENT_LENGTH = 10 * 1024 * 1024
    # pool_pre_ping evita errores por conexiones cerradas por el servidor,
    # muy comunes en Heroku Postgres tras periodos de inactividad.
    SQLALCHEMY_ENGINE_OPTIONS = {"pool_pre_ping": True}

    # Zona horaria y moneda operativa del negocio.
    APP_TIMEZONE = "America/Bogota"
    APP_CURRENCY = "COP"

    TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
    TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
    CLOUDINARY_CLOUD_NAME = os.getenv("CLOUDINARY_CLOUD_NAME")
    CLOUDINARY_API_KEY = os.getenv("CLOUDINARY_API_KEY")
    CLOUDINARY_API_SECRET = os.getenv("CLOUDINARY_API_SECRET")
    CLOUDINARY_FOLDER = os.getenv("CLOUDINARY_FOLDER", "densa-niebla/comprobantes")

    @classmethod
    def init_app(cls, app):
        app.config["SQLALCHEMY_DATABASE_URI"] = get_database_url(*cls.DATABASE_URL_VARS)


class DevelopmentConfig(Config):
    """Base local. Aquí se generan y prueban las migraciones."""

    DATABASE_URL_VARS = ("DEV_DATABASE_URL",)

    DEBUG = True
    SECRET_KEY = os.getenv("SECRET_KEY", "clave-solo-para-desarrollo-local")
    SQLALCHEMY_ECHO = os.getenv("SQLALCHEMY_ECHO", "0") == "1"


class TestingConfig(Config):
    """Base de pruebas. Se crea y destruye en cada corrida de tests."""

    DATABASE_URL_VARS = ("TEST_DATABASE_URL", "DEV_DATABASE_URL")

    TESTING = True
    WTF_CSRF_ENABLED = False
    SECRET_KEY = "clave-solo-para-tests"


class ProductionConfig(Config):
    """Heroku. La URL solo puede venir de Config Vars."""

    DATABASE_URL_VARS = ("DATABASE_URL",)

    DEBUG = False
    SESSION_COOKIE_SECURE = True
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    PREFERRED_URL_SCHEME = "https"

    @classmethod
    def init_app(cls, app):
        super().init_app(app)
        if not app.config.get("SECRET_KEY"):
            raise RuntimeError(
                "SECRET_KEY es obligatoria en produccion. "
                "Definela en Heroku Config Vars."
            )


config_by_name = {
    "development": DevelopmentConfig,
    "testing": TestingConfig,
    "production": ProductionConfig,
}
