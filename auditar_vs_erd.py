r"""Compara, columna por columna, los modelos contra las tablas del ERD.

Extrae las columnas declaradas en las tablas markdown del ERD logico y las
contrasta con Base.metadata. Reporta faltantes y sobrantes por tabla.

Uso:
    python auditar_vs_erd.py                 # busca el ERD junto a este script
    python auditar_vs_erd.py ruta\al\ERD.md  # o le pasas la ruta
"""
from __future__ import annotations
import re, sys
from pathlib import Path
AQUI = Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI))
from app.models import Base

NOMBRE_ERD = "ERD_Logico_Densa_Niebla_v1.md"


def localizar_erd() -> Path:
    """Busca el ERD: primero el argumento, luego junto al script, luego arriba."""
    if len(sys.argv) > 1:
        p = Path(sys.argv[1]).expanduser()
        if not p.is_file():
            sys.exit(f"[ERROR] No existe el archivo indicado: {p}")
        return p
    for cand in (AQUI / NOMBRE_ERD, AQUI.parent / NOMBRE_ERD,
                 AQUI / "docs" / NOMBRE_ERD, AQUI.parent / "docs" / NOMBRE_ERD):
        if cand.is_file():
            return cand
    sys.exit(
        f"[ERROR] No encontre {NOMBRE_ERD}.\n"
        f"        Es el ERD logico aprobado, el mismo que se entrego en markdown.\n"
        f"        Deja el archivo junto a este script ({AQUI}) o pasa la ruta:\n"
        f"        python auditar_vs_erd.py C:\\ruta\\a\\{NOMBRE_ERD}"
    )


ERD = localizar_erd()
print(f"ERD: {ERD}")
AUDIT_COLS = {"created_at","updated_at","created_by_id","updated_by_id"}

lines = ERD.read_text(encoding="utf-8").splitlines()
tables: dict[str,set[str]] = {}
current = None
for ln in lines:
    m = re.match(r"^### \d+\.\d+ `([a-z_]+)`", ln)
    if m:
        current = m.group(1); tables[current] = set(); continue
    if re.match(r"^#{2,3} ", ln) and not re.match(r"^### \d+\.\d+ `", ln):
        current = None
    if current == "app_settings" and ln.startswith("| `key` | Tipo |"):
        current = None   # empieza la tabla de claves de siembra, no son columnas
    if current and ln.startswith("|"):
        cell = ln.split("|")[1].strip()
        c = re.match(r"^`([a-z_0-9]+)`$", cell)
        if c:
            tables[current].add(c.group(1))
        elif cell == "Auditoría":
            # "Completa" -> las 4 columnas; si el ERD lista created_at/updated_at
            # explicitamente, la tabla es de catalogo y solo lleva esas dos.
            note = ln.split("|")[4].strip() if len(ln.split("|")) > 4 else ""
            if "Completa" in note:
                tables[current] |= AUDIT_COLS
            else:
                tables[current] |= {"created_at", "updated_at"}

md = Base.metadata
problems = 0
for t in sorted(tables):
    if t not in md.tables:
        print(f"X {t}: no existe en los modelos"); problems += 1; continue
    erd_cols = tables[t]
    model_cols = set(md.tables[t].columns.keys())
    missing = sorted(erd_cols - model_cols)
    extra = sorted(model_cols - erd_cols)
    if missing:
        print(f"X {t}: FALTAN {missing}"); problems += 1
    if extra:
        print(f"! {t}: adicionales {extra}")
print(f"\nTablas comparadas: {len(tables)}  |  columnas del ERD: {sum(len(v) for v in tables.values())}")
print("SIN OMISIONES" if problems == 0 else f"PROBLEMAS: {problems}")
