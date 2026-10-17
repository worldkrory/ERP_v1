"""Ficha y edición puntual. Registrar este blueprint además del módulo existente."""
import json
import secrets
from datetime import date, datetime, timezone
from urllib.parse import urlsplit

from flask import Blueprint, abort, current_app, redirect, render_template, request, session, url_for
from flask_login import current_user, login_required
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import joinedload, selectinload

from app.extensions import db
from app.models.party import Party
from app.models.price import PriceList
from app.security.permissions import require_role
from app.parties.editor_fields import EDITORS, FIELDS, HINTS, SECTIONS, EditValidationError, plain, proposed_values, version_of

parties_editor_bp = Blueprint("parties_editor", __name__, template_folder="templates")
SYSTEM_FIELDS = {"revision", "editor_csrf", "csrf_token", "confirm_sensitive"}


def _admin():
    return current_user.has_role("ADMIN")


def _party(party_id, lock=False):
    statement = select(Party).where(Party.id == party_id)
    if lock:
        statement = statement.execution_options(populate_existing=True).with_for_update()
    else:
        statement = statement.options(selectinload(Party.party_roles), joinedload(Party.default_price_list))
    party = db.session.scalar(statement)
    if party is None:
        abort(404)
    if not _admin() and not party.has_role("CUSTOMER"):
        abort(403)
    return party


def _allowed(party, key):
    return _admin() or (not EDITORS[key][3] and party.is_active and party.has_role("CUSTOMER"))


def _spec(key):
    if key not in EDITORS:
        abort(404)
    return EDITORS[key]


def _signer():
    return URLSafeTimedSerializer(current_app.config["SECRET_KEY"], salt="dn-party-field-editor-v1")


def _csrf():
    if "party_editor_csrf" not in session:
        session["party_editor_csrf"] = secrets.token_urlsafe(32)
    return session["party_editor_csrf"]


def _check_request():
    if request.content_length and request.content_length > 131072:
        abort(413)
    origin = request.headers.get("Origin")
    if origin and urlsplit(origin).netloc.lower() != request.host.lower():
        abort(403)
    expected = session.get("party_editor_csrf", "")
    supplied = request.form.get("editor_csrf", "")
    if not expected or not secrets.compare_digest(expected, supplied):
        abort(403, description="Token de edición no válido. Recarga la ficha.")


def _display(party, name):
    value = getattr(party, name)
    if value is None or value == "":
        return "Sin registrar"
    spec = FIELDS[name]
    if spec.kind == "bool":
        return "Sí" if value else "No"
    if spec.kind == "select":
        return dict(spec.choices).get(value, str(value))
    if spec.kind == "list":
        return " · ".join(str(v) if not isinstance(v, (dict,list)) else "Elemento estructurado" for v in value) or "Sin responsabilidades registradas"
    if spec.kind == "price":
        item = db.session.get(PriceList, value)
        return f"{item.code} · {item.name}" if item else f"Lista #{value} no disponible"
    return str(plain(value))


def _view(party, key, posted=None, error=None, conflict=False, saved=False):
    title, section, names, sensitive = _spec(key)
    inputs = []
    for name in names:
        spec = FIELDS[name]
        current = getattr(party, name)
        if posted is not None and name in posted:
            value = posted[name]
        elif spec.kind == "list":
            value = json.dumps(current, ensure_ascii=False)
        elif spec.kind == "bool":
            value = "true" if current else "false"
        else:
            value = str(plain(current)) if current is not None else ""
        options = list(spec.choices)
        if spec.kind == "bool":
            options = [("true", "Sí"), ("false", "No")]
        if spec.kind == "price":
            today = date.today()
            conditions = (PriceList.is_active.is_(True) & (PriceList.valid_from <= today) & or_(PriceList.valid_to.is_(None), PriceList.valid_to >= today))
            if party.default_price_list_id:
                conditions = or_(conditions, PriceList.id == party.default_price_list_id)
            options = [(str(p.id), f"{p.code} · {p.name}" + (" · No vigente" if not p.is_current else "")) for p in db.session.scalars(select(PriceList).where(conditions).order_by(PriceList.name)).all()]
        inputs.append(dict(name=name, label=spec.label, kind=spec.kind, nullable=spec.nullable,
                           maximum=spec.maximum, options=options, value=value, display=_display(party, name)))
    revision = posted.get("revision", "") if posted is not None else _signer().dumps({"party":party.id, "editor":key, "actor":current_user.id, "version":version_of(party)})
    global_csrf = None
    if "csrf" in current_app.extensions:
        from flask_wtf.csrf import generate_csrf
        global_csrf = generate_csrf()
    return dict(party=party, key=key, title=title, section=section, inputs=inputs,
                sensitive=sensitive, can_edit=_allowed(party,key), hint=HINTS.get(key),
                revision=revision, editor_csrf=_csrf(), global_csrf=global_csrf,
                error=error, conflict=conflict, saved=saved)


def _headers():
    return {"Cache-Control":"no-store", "Vary":"HX-Request, HX-History-Restore-Request"}


def _partial():
    return request.headers.get("HX-Request") == "true" and request.headers.get("HX-History-Restore-Request") != "true"


def _full(party, editing=None, posted=None, error=None, conflict=False, status=200, open_section=None):
    groups = []
    for section, label in SECTIONS:
        items = [_view(party,key,posted if key == editing else None,error if key == editing else None,conflict if key == editing else False) for key,spec in EDITORS.items() if spec[1] == section]
        groups.append(dict(key=section, label=label, items=items, open=section == "identificacion" or section == open_section or any(i["key"] == editing for i in items)))
    return render_template("parties/editor/detail.html", party=party, groups=groups,
                           editing=editing, meta_oob=False), status, _headers()


@parties_editor_bp.get("/clientes/<int:party_id>/ficha")
@login_required
@require_role("ADMIN", "VENTAS")
def detail(party_id):
    return _full(_party(party_id), open_section=request.args.get("section"))


@parties_editor_bp.get("/clientes/<int:party_id>/datos/<key>")
@login_required
@require_role("ADMIN", "VENTAS")
def read_field(party_id, key):
    _spec(key)
    party = _party(party_id)
    if not _partial():
        return redirect(url_for("parties_editor.detail", party_id=party.id, section=EDITORS[key][1]) + "#party-field-" + key)
    return render_template("parties/editor/_field.html", **_view(party,key)), 200, _headers()


@parties_editor_bp.route("/clientes/<int:party_id>/editar/<key>", methods=["GET","POST"])
@login_required
@require_role("ADMIN", "VENTAS")
def edit_field(party_id, key):
    spec = _spec(key)
    if request.method == "GET":
        party = _party(party_id)
        if not _allowed(party,key):
            abort(403)
        if _partial():
            return render_template("parties/editor/_form.html", **_view(party,key)), 200, _headers()
        return _full(party, editing=key)

    _check_request()
    party = _party(party_id, lock=True)
    if not _allowed(party,key):
        abort(403)
    posted = request.form.to_dict()
    error, conflict, status = None, False, 422
    try:
        try:
            token = _signer().loads(posted.get("revision", ""), max_age=1800)
        except (BadSignature, SignatureExpired) as exc:
            raise EditValidationError("La edición venció o no es válida. Recarga los valores actuales.") from exc
        if token.get("party") != party.id or token.get("editor") != key or token.get("actor") != current_user.id:
            abort(403)
        if token.get("version") != version_of(party):
            conflict, status = True, 409
            raise EditValidationError("El tercero cambió desde que abriste el editor. No se guardó nada. Recarga los valores actuales antes de continuar.")
        if set(request.form) - set(spec[2]) - SYSTEM_FIELDS:
            raise EditValidationError("La solicitud contiene campos no admitidos para este editor.")
        if any(len(request.form.getlist(name)) != 1 for name in spec[2]):
            raise EditValidationError("Cada campo debe enviarse exactamente una vez.")
        if spec[3] and posted.get("confirm_sensitive") != "yes":
            raise EditValidationError("Confirma que verificaste los datos antes de guardar.")
        values = proposed_values(party,key,posted)
        if "default_price_list_id" in values and values["default_price_list_id"] is not None and values["default_price_list_id"] != party.default_price_list_id:
            price = db.session.get(PriceList,values["default_price_list_id"])
            if price is None or not price.is_current:
                raise EditValidationError("La lista seleccionada no está activa y vigente.")
        changed = [name for name,value in values.items() if value != getattr(party,name)]
        for name in changed:
            setattr(party,name,values[name])
        if changed:
            party.updated_by_id = current_user.id
            party.updated_at = datetime.now(timezone.utc)
            db.session.flush()
        db.session.commit()
        current_app.logger.info("PARTY_FIELD_EDIT actor=%s party=%s editor=%s fields=%s", current_user.id,party.id,key,','.join(changed) or 'none')
    except EditValidationError as exc:
        error = str(exc)
        db.session.rollback()
    except IntegrityError:
        db.session.rollback()
        error, status = "No se guardó el cambio: documento duplicado o restricción de integridad. Revisa los valores y recarga si el registro cambió.",409
    except SQLAlchemyError:
        db.session.rollback()
        current_app.logger.exception("Error de base al editar Party %s",party_id)
        error, status = "No se pudo completar el cambio. Busca el dato actual antes de intentar nuevamente.",503
    party = _party(party_id)
    if error:
        if _partial():
            return render_template("parties/editor/_form.html", **_view(party,key,posted,error,conflict)), status, _headers()
        return _full(party, editing=key, posted=posted,error=error,conflict=conflict,status=status)
    if _partial():
        return render_template("parties/editor/_saved.html", **_view(party,key,saved=True)), 200, _headers()
    return redirect(url_for("parties_editor.detail", party_id=party.id, section=EDITORS[key][1]) + "#party-field-" + key, code=303)
