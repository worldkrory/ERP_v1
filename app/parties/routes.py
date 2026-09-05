from __future__ import annotations

from datetime import date
from types import SimpleNamespace

from flask import Blueprint, jsonify, render_template, request
from flask_login import login_required, current_user
from app.auth.decorators import require_role, admin_only, audit_action
from sqlalchemy import or_
from sqlalchemy.exc import SQLAlchemyError

from app.extensions import db
from app.models.party import DOCUMENT_TYPES, PARTY_ROLE_CODES, Party, PartyRole

parties_bp = Blueprint("parties", __name__, url_prefix="/api/v1")
parties_admin_bp = Blueprint(
    "parties_admin", __name__, template_folder="templates", url_prefix=""
)


@parties_bp.get("/customers")
def list_customers():
    try:
        customers = _customer_query().all()
        return jsonify([_customer_payload(customer) for customer in customers])
    except SQLAlchemyError:
        db.session.rollback()
        return jsonify(_demo_customers())


@parties_bp.post("/customers")
def create_customer():
    payload = request.get_json(silent=True) or {}
    try:
        document_type = str(payload.get("document_type") or "CC")
        document_number = str(payload.get("document_number") or "").strip()
        legal_name = str(payload.get("legal_name") or "").strip()
        first_name = str(payload.get("first_name") or "").strip() or None
        last_name = str(payload.get("last_name") or "").strip() or None
        if document_type not in DOCUMENT_TYPES:
            raise ValueError("El tipo de documento no es válido.")
        if not document_number or not legal_name:
            raise ValueError("Documento y nombre son obligatorios.")
        if document_type == "NIT" and payload.get("verification_digit") in (None, ""):
            raise ValueError("El NIT necesita dígito de verificación.")
        if payload.get("party_type", "NATURAL") == "NATURAL" and not first_name and not last_name:
            first_name, last_name = legal_name, legal_name

        party = Party(
            party_type=str(payload.get("party_type") or "NATURAL"),
            document_type=document_type,
            document_number=document_number,
            verification_digit=(
                int(payload["verification_digit"])
                if payload.get("verification_digit") not in (None, "")
                else None
            ),
            legal_name=legal_name,
            trade_name=str(payload.get("trade_name") or "").strip() or None,
            first_name=first_name,
            last_name=last_name,
            email=str(payload.get("email") or "").strip() or None,
            phone=str(payload.get("phone") or "").strip() or None,
            whatsapp=str(payload.get("whatsapp") or "").strip() or None,
            payment_term_days=int(payload.get("payment_term_days") or 0),
            credit_limit=payload.get("credit_limit") or None,
        )
        requested_roles = payload.get("roles") or []
        if not isinstance(requested_roles, list):
            raise ValueError("Los roles deben enviarse como una lista.")
        allowed_roles = {"CAFETERIA", "INTERMEDIARY"}
        roles = {str(role) for role in requested_roles} & allowed_roles
        roles.add("CUSTOMER")
        party.party_roles = [
            PartyRole(role_code=role, valid_from=date.today())
            for role in sorted(roles)
        ]
        db.session.add(party)
        db.session.commit()
        return jsonify(_customer_payload(party)), 201
    except SQLAlchemyError:
        db.session.rollback()
        return jsonify({"error": "La base de datos aún no está migrada."}), 503
    except (TypeError, ValueError) as exc:
        db.session.rollback()
        return jsonify({"error": str(exc)}), 400


@parties_admin_bp.get("/clientes")
@login_required
@require_role("VENTAS", "ADMIN")
def customers_admin_page():
    demo_mode = False
    try:
        customers = _customer_query().all()
    except SQLAlchemyError:
        db.session.rollback()
        customers = [SimpleNamespace(**customer) for customer in _demo_customers()]
        demo_mode = True
    return render_template(
        "customers_admin.html",
        customers=customers,
        document_types=DOCUMENT_TYPES,
        customer_roles=("CUSTOMER", "CAFETERIA", "INTERMEDIARY"),
        demo_mode=demo_mode,
    )


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
