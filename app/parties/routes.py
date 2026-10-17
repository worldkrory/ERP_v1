from __future__ import annotations

from datetime import date
from types import SimpleNamespace

from flask import Blueprint, current_app, jsonify, render_template, request
from flask_login import login_required, current_user
from app.auth.decorators import require_role, admin_only, audit_action
from sqlalchemy import or_
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from app.extensions import db
from app.models.party import DOCUMENT_TYPES, PARTY_ROLE_CODES, Party, PartyRole

from app.security.permissions import require_role

from app.parties.workspace import render_customers_workspace

parties_bp = Blueprint("parties", __name__, url_prefix="/api/v1")
parties_admin_bp = Blueprint(
    "parties_admin", __name__, template_folder="templates", url_prefix=""
)


@parties_bp.get("/customers")
@login_required
@require_role("ADMIN", "VENTAS")
def list_customers():

    try:
        customers = _customer_query().all()
        return jsonify([_customer_payload(customer) for customer in customers])
    except SQLAlchemyError:
        db.session.rollback()
        return jsonify(_demo_customers())
    


@parties_bp.post("/customers")
@login_required
@require_role("ADMIN", "VENTAS")
def create_customer():
    payload = request.get_json(silent=True) or {}
    try:
        
        party_type = str(
            payload.get("party_type") or "NATURAL"
        ).strip()

        document_type = str(
            payload.get("document_type") or "CC"
        ).strip()

        document_number = str(
            payload.get("document_number") or ""
        ).strip()

        legal_name = str(
            payload.get("legal_name") or ""
        ).strip()

        first_name = str(
            payload.get("first_name") or ""
        ).strip() or None

        last_name = str(
            payload.get("last_name") or ""
        ).strip() or None

        if party_type not in ("NATURAL", "JURIDICA"):
            raise ValueError("El tipo de persona no es válido.")

        if document_type not in DOCUMENT_TYPES:
            raise ValueError("El tipo de documento no es válido.")

        if not document_number:
            raise ValueError("El número de documento es obligatorio.")

        if len(document_number) > 30:
            raise ValueError("El documento admite máximo 30 caracteres.")

        if party_type == "NATURAL":
            if not first_name:
                raise ValueError(
                    "Para una persona natural debes indicar "
                    "al menos sus nombres."
                )

            if len(first_name) > 100:
                raise ValueError(
                    "Los nombres admiten máximo 100 caracteres."
                )

            if last_name is not None and len(last_name) > 100:
                raise ValueError(
                    "Los apellidos admiten máximo 100 caracteres."
                )

            # Apellido desconocido: vacío, no NULL.
            last_name = last_name or ""

            legal_name = " ".join(
                part
                for part in (first_name, last_name)
                if part
            )

        else:
            if not legal_name:
                raise ValueError("La razón social es obligatoria.")

            if first_name or last_name:
                raise ValueError(
                    "Los nombres de representantes o contactos "
                    "no deben registrarse como nombres de la empresa."
                )

        if len(legal_name) > 200:
            raise ValueError(
                "El nombre completo o razón social "
                "admite máximo 200 caracteres."
            )

        if (
            document_type == "NIT"
            and payload.get("verification_digit") in (None, "")
        ):
            raise ValueError(
                "El NIT necesita dígito de verificación."
            )

        party = Party(
            party_type=party_type,
            document_type=document_type,
            document_number=document_number,
            verification_digit=(
                int(payload["verification_digit"])
                if payload.get("verification_digit") not in (None, "")
                else None
            ),
            legal_name=legal_name,
            trade_name=(
                str(payload.get("trade_name") or "").strip()
                or None
            ),
            first_name=first_name,
            last_name=last_name,
            email=(
                str(payload.get("email") or "").strip()
                or None
            ),
            phone=(
                str(payload.get("phone") or "").strip()
                or None
            ),
            whatsapp=(
                str(payload.get("whatsapp") or "").strip()
                or None
            ),
            payment_term_days=int(
                payload.get("payment_term_days") or 0
            ),
            credit_limit=payload.get("credit_limit") or None,
        )

        requested_roles = payload.get("roles") or []

        if not isinstance(requested_roles, list):
            raise ValueError(
                "Los roles deben enviarse como una lista."
            )

        allowed_roles = {"CAFETERIA", "INTERMEDIARY"}

        roles = {
            str(role)
            for role in requested_roles
        } & allowed_roles

        roles.add("CUSTOMER")

        party.party_roles = [
            PartyRole(
                role_code=role,
                valid_from=date.today(),
            )
            for role in sorted(roles)
        ]

        db.session.add(party)
        db.session.commit()

        return jsonify(_customer_payload(party)), 201
    
    except IntegrityError as exc:
        db.session.rollback()

        original = exc.orig

        sqlstate = (
            getattr(original, "sqlstate", None)
            or getattr(original, "pgcode", None)
        )

        diagnostic = getattr(original, "diag", None)

        constraint_name = getattr(
            diagnostic,
            "constraint_name",
            None,
        )

        if (
            sqlstate == "23505"
            and constraint_name == "uq_parties_document_type"
        ):
            return jsonify({
                "error": (
                    "Ya existe un tercero con este tipo "
                    "y número de documento. Búscalo en el "
                    "directorio para consultar o modificar "
                    "sus datos."
                ),
                "code": "DUPLICATE_DOCUMENT",
                "field": "document_number",
            }), 409

        current_app.logger.warning(
            "Registro de cliente rechazado por integridad: "
            "sqlstate=%s constraint=%s",
            sqlstate,
            constraint_name,
        )

        return jsonify({
            "error": (
                "No fue posible guardar el cliente porque "
                "algún dato incumple una restricción. "
                "Revisa los valores ingresados."
            ),
            "code": "INVALID_CUSTOMER_DATA",
        }), 422

    except (TypeError, ValueError) as exc:
        db.session.rollback()

        return jsonify({
            "error": str(exc),
            "code": "VALIDATION_ERROR",
        }), 400

    except SQLAlchemyError:
        db.session.rollback()

        current_app.logger.exception(
            "Error de base de datos al registrar un cliente"
        )

        return jsonify({
            "error": (
                "Ocurrió un error al guardar el cliente. "
                "Si el problema continúa, contacta "
                "al administrador."
            ),
            "code": "DATABASE_ERROR",
        }), 500


@parties_admin_bp.get("/clientes")
@login_required
@require_role("ADMIN", "VENTAS")
def customers_admin_page():
    return render_customers_workspace()

def _customer_query():
    today = date.today()
    return (
        db.session.query(Party)
        .join(PartyRole, PartyRole.party_id == Party.id)
        .filter(
            Party.is_active.is_(True),
            PartyRole.role_code == "CUSTOMER",
            PartyRole.valid_from <= today,
            or_(PartyRole.valid_to.is_(None), PartyRole.valid_to >= today),
        )
        .order_by(Party.legal_name)
        .distinct()
    )


def _customer_payload(customer) -> dict:
    return {
        "id": customer.id,
        "display_name": customer.display_name,
        "document": customer.document_full,
        "document_type": customer.document_type,
        "document_number": customer.document_number,
        "party_type": customer.party_type,
        "email": customer.email or "",
        "phone": customer.phone or "",
        "payment_term_days": customer.payment_term_days,
        "roles": sorted(
            role.role_code
            for role in getattr(customer, "party_roles", [])
            if role.role_code in PARTY_ROLE_CODES
        ),
    }


def _demo_customers() -> list[dict]:
    return [
        {
            "id": 1,
            "display_name": "Cafetería La Montaña",
            "document": "NIT DEMO-1",
            "document_full": "NIT DEMO-1",
            "document_type": "NIT",
            "document_number": "DEMO-1",
            "party_type": "JURIDICA",
            "email": "compras@lamontana.demo",
            "phone": "+57 300 000 0001",
            "payment_term_days": 30,
            "roles": ["CUSTOMER", "CAFETERIA"],
        },
        {
            "id": 2,
            "display_name": "María Fernanda Torres",
            "document": "CC DEMO-2",
            "document_full": "CC DEMO-2",
            "document_type": "CC",
            "document_number": "DEMO-2",
            "party_type": "NATURAL",
            "email": "maria.demo@example.com",
            "phone": "+57 300 000 0002",
            "payment_term_days": 0,
            "roles": ["CUSTOMER"],
        },
    ]
