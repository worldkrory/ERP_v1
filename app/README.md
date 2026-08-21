# Landing Bourbon Rosado — Densa Niebla

Archivos:
- `templates/microlote_bourbon_rosado.html`
- `static/css/microlote.css`

### Ruta Flask

```python
@app.route("/microlote/bourbon-rosado")
def bourbon_rosado():
    return render_template("microlote_bourbon_rosado.html")
```

El QR de la bolsa debería apuntar a la ruta del microlote, no directamente a Instagram.
Así la URL puede mantenerse aunque después cambies los Reels o la estructura de Instagram.

Antes de publicar:
1. Reemplazar el bloque de fotografía por una foto real de la finca/microlote.
2. Confirmar el usuario de Instagram.
3. Si existe número de microlote/cosecha/lote, añadirlo.
