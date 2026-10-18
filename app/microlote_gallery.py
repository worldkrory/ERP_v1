"""Galeria editorial Bourbon. Rutas publicas de lectura, sin acceso al ERP."""
import os
from urllib.parse import urlsplit
from flask import Blueprint, abort, current_app, redirect, render_template, request, url_for

bourbon_gallery_bp = Blueprint("bourbon_gallery", __name__)
CHAPTERS = {
    "origen": {"number":"01", "label":"Origen", "title":"Un café tiene un lugar.", "text":"Este Bourbon Rosado nace en las montañas de Guavatá, Santander, en una finca rodeada por el paisaje que inspira a Densa Niebla.", "note":"Guavatá · Santander · Colombia"},
    "proceso": {"number":"02", "label":"Proceso", "title":"Detrás de la taza, un recorrido.", "text":"Cada lote tiene un origen, un proceso y unas manos detrás. La información comercial vigente de esta referencia se consulta en su ficha de la tienda.", "note":"Los datos del lote no se sustituyen por la narrativa."},
    "taza": {"number":"03", "label":"Tu taza", "title":"La historia continúa contigo.", "text":"Descubre la presentación que quieres llevar a tu taza. Consulta en la tienda las opciones, el precio y la disponibilidad actuales.", "note":"Elegir presentación no confirma una venta."},
}


def _media(value, fallback=None):
    value = str(value or "").strip()
    if not value:
        return fallback
    parsed = urlsplit(value)
    if parsed.scheme == "https" and parsed.netloc:
        return value
    if not parsed.scheme and not parsed.netloc and value.startswith("/") and not value.startswith("//"):
        return value
    return fallback


def render_bourbon_gallery():
    key = request.args.get("chapter", "origen")
    if key not in CHAPTERS:
        key = "origen"
    image = _media(current_app.config.get("BOURBON_GALLERY_IMAGE_URL") or os.getenv("BOURBON_GALLERY_IMAGE_URL"),
                   url_for("static", filename="img/products/bourbon-rosado/bolsa-frontal.png"))
    video = _media(current_app.config.get("BOURBON_GALLERY_VIDEO_URL") or os.getenv("BOURBON_GALLERY_VIDEO_URL"))
    return render_template("microlote_gallery/bourbon.html", chapters=CHAPTERS,
                           chapter_key=key, chapter=CHAPTERS[key], image_url=image, video_url=video)


@bourbon_gallery_bp.get("/microlote/bourbon-rosado/galeria")
def preview():
    return render_bourbon_gallery()


@bourbon_gallery_bp.get("/microlote/bourbon-rosado/capitulo/<key>")
def chapter_fragment(key):
    if key not in CHAPTERS:
        abort(404)
    is_partial = request.headers.get("HX-Request") == "true" and request.headers.get("HX-History-Restore-Request") != "true"
    if not is_partial:
        endpoint = "bourbon_gallery.preview" if request.args.get("preview") == "1" else "bourbon_rosado"
        return redirect(url_for(endpoint, chapter=key, _anchor="cuaderno"), code=302)
    return render_template("microlote_gallery/_chapter.html", chapter_key=key, chapter=CHAPTERS[key]), 200, {
        "Cache-Control":"no-store", "Vary":"HX-Request, HX-History-Restore-Request"
    }
