"""Registro explícito de datos editables de Party y validaciones puras."""
import hashlib
import json
import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation


class EditValidationError(ValueError):
    pass


@dataclass(frozen=True)
class Field:
    label: str
    kind: str = "text"
    nullable: bool = True
    maximum: int = 0
    choices: tuple = ()


FIELDS = {
    "party_type": Field("Tipo de persona", "select", False, choices=(("NATURAL", "Persona natural"), ("JURIDICA", "Empresa"))),
    "first_name": Field("Nombres", maximum=100),
    "last_name": Field("Apellidos", maximum=100),
    "document_type": Field("Tipo de documento", "select", False, choices=tuple((v, v) for v in ("CC", "NIT", "CE", "PAS", "TI", "RC", "PEP", "NIT_EXT"))),
    "document_number": Field("Número de documento", nullable=False, maximum=30),
    "verification_digit": Field("Dígito de verificación", "digit"),
    "legal_name": Field("Nombre completo / razón social", nullable=False, maximum=200),
    "trade_name": Field("Nombre comercial", maximum=200),
    "email": Field("Correo electrónico", "email", maximum=255),
    "phone": Field("Teléfono", maximum=30),
    "whatsapp": Field("WhatsApp", maximum=30),
    "tax_regime": Field("Régimen fiscal", "select", choices=tuple((v, v.replace("_", " ").title()) for v in ("SIMPLIFICADO", "COMUN", "GRAN_CONTRIBUYENTE", "NO_RESPONSABLE_IVA", "REGIMEN_SIMPLE"))),
    "tax_responsibilities": Field("Responsabilidades fiscales", "list", False),
    "is_vat_withholding_agent": Field("Agente de retención de IVA", "bool", False),
    "country_code": Field("Código de país", "country", False, 2),
    "department_code": Field("Código de departamento", "department", maximum=2),
    "municipality_code": Field("Código de municipio", "municipality", maximum=5),
    "credit_limit": Field("Cupo de crédito", "money"),
    "payment_term_days": Field("Plazo de pago en días", "days", False),
    "default_price_list_id": Field("Lista de precios predeterminada", "price"),
    "notes": Field("Notas", "textarea", maximum=20000),
    "is_active": Field("Estado activo", "bool", False),
}

# label, section, allowed properties, requires ADMIN
EDITORS = {
    "documento": ("Documento de identificación", "identificacion", ("document_type", "document_number", "verification_digit"), True),
    "persona": ("Tipo de persona y nombres", "identificacion", ("party_type", "first_name", "last_name"), True),
    "legal_name": ("Nombre completo / razón social", "identificacion", ("legal_name",), True),
    "trade_name": ("Nombre comercial", "identificacion", ("trade_name",), False),
    "email": ("Correo electrónico", "contacto", ("email",), False),
    "phone": ("Teléfono", "contacto", ("phone",), False),
    "whatsapp": ("WhatsApp", "contacto", ("whatsapp",), False),
    "tax_regime": ("Régimen fiscal", "fiscal", ("tax_regime",), True),
    "tax_responsibilities": ("Responsabilidades fiscales", "fiscal", ("tax_responsibilities",), True),
    "is_vat_withholding_agent": ("Agente de retención de IVA", "fiscal", ("is_vat_withholding_agent",), True),
    "ubicacion": ("País, departamento y municipio", "ubicacion", ("country_code", "department_code", "municipality_code"), True),
    "credit_limit": ("Cupo de crédito", "comercial", ("credit_limit",), True),
    "payment_term_days": ("Plazo de pago", "comercial", ("payment_term_days",), True),
    "default_price_list_id": ("Lista de precios predeterminada", "comercial", ("default_price_list_id",), True),
    "notes": ("Notas", "notas", ("notes",), False),
    "is_active": ("Activar o desactivar", "estado", ("is_active",), True),
}
SECTIONS = (("identificacion", "Identificación"), ("contacto", "Contacto"),
            ("fiscal", "Datos fiscales"), ("ubicacion", "Ubicación"),
            ("comercial", "Condiciones comerciales"), ("notas", "Notas"), ("estado", "Estado"))
HINTS = {
    "documento": "Tipo, número y dígito se guardan juntos. Corrige datos del mismo tercero; si es otra persona o empresa, crea un registro nuevo.",
    "persona": (
        "Para persona natural se requieren nombres. "
        "Los apellidos son opcionales. "
        "El nombre completo no se recalcula automáticamente "
        "desde este editor."
    ),
    "tax_regime": "Opciones admitidas por tu modelo. Selecciona el valor documentado del tercero; no se determina su situación fiscal automáticamente.",
    "tax_responsibilities": "Añade cada código como texto. No se incluye un catálogo fiscal oficial. Los elementos existentes conservan su tipo si no los eliminas.",
    "ubicacion": "CO utiliza departamento de 2 dígitos y municipio de 5. Se comprueba formato y prefijo, no existencia en un catálogo geográfico.",
    "credit_limit": "Sin separador de miles. Punto o coma para decimales. Vacío significa sin configurar; 0 es un cupo de cero.",
    "default_price_list_id": "Solo se pueden asignar listas activas y vigentes. Una asignación anterior inactiva se puede conservar o quitar.",
    "is_active": "Un tercero inactivo desaparece del directorio de clientes activos. No se elimina ni se cambian sus documentos relacionados.",
}


def plain(value):
    if isinstance(value, Decimal):
        return format(value, "f")
    return value


def version_of(party):
    snapshot = {key: plain(getattr(party, key)) for key in FIELDS}
    snapshot["updated_at"] = party.updated_at.isoformat() if party.updated_at else None
    return hashlib.sha256(json.dumps(snapshot, sort_keys=True, ensure_ascii=False, default=str).encode()).hexdigest()


def parse_value(name, raw):
    spec = FIELDS[name]
    value = str(raw).strip()
    if not value:
        if spec.nullable:
            return None
        raise EditValidationError(f"{spec.label}: el valor es obligatorio.")
    if spec.maximum and len(value) > spec.maximum:
        raise EditValidationError(f"{spec.label}: máximo {spec.maximum} caracteres.")
    if spec.kind == "bool":
        if value not in ("true", "false"):
            raise EditValidationError(f"{spec.label}: selecciona Sí o No.")
        return value == "true"
    if spec.kind == "select":
        if value not in dict(spec.choices):
            raise EditValidationError(f"{spec.label}: opción no válida.")
    if spec.kind in ("digit", "days", "price"):
        if not re.fullmatch(r"[0-9]+", value):
            raise EditValidationError(f"{spec.label}: utiliza un número entero.")
        if len(value) > 20:
            raise EditValidationError(f"{spec.label}: número demasiado largo.")
        number = int(value)
        low, high = {"digit": (0,9), "days": (0,32767), "price": (1,9223372036854775807)}[spec.kind]
        if not low <= number <= high:
            raise EditValidationError(f"{spec.label}: valor fuera del rango permitido.")
        return number
    if spec.kind == "money":
        if len(value) > 64:
            raise EditValidationError("Cupo de crédito: importe demasiado largo.")
        try:
            number = Decimal(value.replace(",", "."))
        except InvalidOperation as exc:
            raise EditValidationError("Cupo de crédito: importe no válido.") from exc
        if not number.is_finite() or number < 0 or number > Decimal("99999999999999.99"):
            raise EditValidationError("Cupo de crédito: importe fuera del rango permitido.")
        if number != number.quantize(Decimal("0.01")):
            raise EditValidationError("Cupo de crédito: máximo dos decimales.")
        return number.quantize(Decimal("0.01"))
    if spec.kind == "list":
        if len(value) > 20000:
            raise EditValidationError("Responsabilidades: contenido demasiado extenso.")
        def invalid_constant(constant):
            raise ValueError(constant)
        try:
            result = json.loads(value, parse_constant=invalid_constant)
        except (ValueError, RecursionError) as exc:
            raise EditValidationError("Responsabilidades: lista no válida.") from exc
        if not isinstance(result, list) or len(result) > 100:
            raise EditValidationError("Responsabilidades: se admite una lista de hasta 100 elementos.")
        return result
    if spec.kind == "email" and not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", value):
        raise EditValidationError("Correo electrónico: formato no válido.")
    if spec.kind == "country":
        value = value.upper()
        if not re.fullmatch(r"[A-Z]{2}", value):
            raise EditValidationError("País: utiliza dos letras, por ejemplo CO.")
    if spec.kind in ("department", "municipality"):
        length = 2 if spec.kind == "department" else 5
        if not re.fullmatch(r"[0-9]{%d}" % length, value):
            raise EditValidationError(f"{spec.label}: se requieren {length} dígitos.")
    return value


def proposed_values(party, key, submitted):
    names = EDITORS[key][2]

    # Copia los valores actuales sin modificar todavía el modelo.
    result = {
        name: getattr(party, name)
        for name in FIELDS
    }

    # Aplica todos los campos recibidos del editor.
    for name in names:
        if name not in submitted:
            raise EditValidationError(
                f"Falta el campo {FIELDS[name].label}."
            )

        result[name] = parse_value(
            name,
            submitted[name],
        )

    # Este bloque va DESPUÉS del for, no dentro.
    if result["party_type"] == "NATURAL":
        if not result["first_name"]:
            raise EditValidationError(
                "Una persona natural necesita al menos sus nombres."
            )

        if "last_name" in names:
            # Conserva el apellido recibido.
            # Solo convierte la ausencia en cadena vacía.
            result["last_name"] = (
                result["last_name"]
                if result["last_name"] is not None
                else ""
            )

    if (
        result["document_type"] == "NIT"
        and result["verification_digit"] is None
    ):
        raise EditValidationError(
            "El documento NIT requiere dígito de verificación."
        )

    if key == "ubicacion":
        country = result["country_code"]
        department = result["department_code"]
        municipality = result["municipality_code"]

        if country != "CO" and (department or municipality):
            raise EditValidationError(
                "Para otro país, quita los códigos locales "
                "de departamento y municipio."
            )

        if municipality and (
            not department
            or not municipality.startswith(department)
        ):
            raise EditValidationError(
                "El municipio debe comenzar por el código "
                "del departamento seleccionado."
            )

    # Devuelve los valores nuevos, no los originales de party.
    return {
        name: result[name]
        for name in names
    }
