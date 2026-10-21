"""Pruebas del analisis del informe por lote (funciones puras; no requieren Flask ni base de datos)."""
import importlib.util
import pathlib
from datetime import date

_spec = importlib.util.spec_from_file_location(
    "lr_analysis", pathlib.Path(__file__).resolve().parents[1] / "app" / "lot_reports" / "analysis.py")
analysis = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(analysis)


def _data():
    ventas = [
        ("V-7", "2026-08-12", 2, 64000, 32450.54), ("V-9", "2026-09-18", 1, 32000, 16225.27),
        ("V-18", "2026-09-29", 1, 32000, 16225.27), ("V-1", "2026-10-03", 1, 32000, 16225.27),
        ("V-24", "2026-10-21", 1, 32000, 16225.27),
    ]
    return {
        "identidad": [{"batch_code": "L-1", "batch_type": "PRODUCED", "status": "ACTIVE", "producto": "Café", "unidad": "UND",
                       "initial_quantity": 119, "unit_cost": 16225.27, "valor_inicial": 1930807.13, "production_date": "2026-09-29",
                       "order_number": "OP-1", "estado_orden": "COMPLETED"}],
        "orden": [{"status": "COMPLETED", "started_at": "x", "completed_at": "x", "total_input_cost": 1748700, "total_process_cost": 294360,
                   "total_overhead_cost": 50000, "total_cost": 2093060, "output_quantity_base": 43.86, "waste_quantity_base": 23.64, "yield_pct": 0.649778}],
        "ventas": [{"sale_number": n, "sale_date": d, "status": "CONFIRMED", "payment_status": "UNPAID", "channel": "RETAIL",
                    "cliente": f"Cliente {n}", "cantidad_base": q, "ingreso_neto": r, "impuesto": 0, "costo_ventas": c,
                    "margen": r - c, "margen_pct": 0.493, "cobrado_atribuido": 0, "por_cobrar_atribuido": r, "due_date": d}
                   for n, d, q, r, c in ventas],
    }


def test_formatos_regionales():
    assert analysis.money(192000) == "$ 192.000"
    assert analysis.money(16225.27, 2) == "$ 16.225,27"
    assert analysis.money(-1738807) == "-$ 1.738.807"
    assert analysis.qty(6) == "6" and analysis.qty(67.5) == "67,50"
    assert analysis.pct(0.493) == "49,3 %" and analysis.pct(None) == "—"


def test_indicadores_del_lote():
    r = analysis.build_report(_data(), date(2026, 10, 21))
    assert r["qty_sold"] == 6 and round(float(r["revenue"]), 2) == 192000
    assert round(float(r["cogs"]), 2) == 97351.62 and round(float(r["margin_pct"]), 3) == 0.493
    assert r["breakeven"] == 61 and r["overdue_count"] == 4 and r["oldest_overdue_days"] == 70
    assert round(float(r["composition"]["share"]), 4) == 0.9225


def test_controles_y_lectura():
    r = analysis.build_report(_data(), date(2026, 10, 21))
    states = {c["name"]: c["state"] for c in r["controls"]}
    assert states["Cartera vencida"] == "REVISAR" and states["Origen: finca registrada"] == "REVISAR"
    assert states["Orden con costeo cerrado"] == "INFO"
    assert r["facts"][0].startswith("Se asignaron a ventas 6 de 119 UND (5,0 %)")


def test_lote_sin_datos_devuelve_none():
    assert analysis.build_report({"identidad": []}) is None
