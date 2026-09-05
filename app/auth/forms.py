"""Formularios de autenticación del ERP."""

from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, SubmitField
from wtforms.validators import DataRequired, Email, Length


class LoginForm(FlaskForm):
    """Formulario de login seguro con CSRF protection."""
    
    email = StringField(
        "Correo electrónico",
        validators=[
            DataRequired(message="El correo es obligatorio"),
            Email(message="Ingresa un correo válido"),
        ],
        render_kw={"class": "form-control", "placeholder": "correo@example.com"}
    )
    
    password = PasswordField(
        "Contraseña",
        validators=[
            DataRequired(message="La contraseña es obligatoria"),
            Length(min=6, message="La contraseña debe tener al menos 6 caracteres"),
        ],
        render_kw={"class": "form-control", "placeholder": "Tu contraseña"}
    )
    
    submit = SubmitField(
        "Iniciar sesión",
        render_kw={"class": "btn btn-primary btn-block"}
    )
