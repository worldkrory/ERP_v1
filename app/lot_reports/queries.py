"""Consultas de solo lectura del informe por lote.

Todas son SELECT. `execute(sql, params)` debe devolver una lista de dicts; en la
aplicacion lo provee routes.py con db.session.execute(text(...)).
El codigo del lote se enlaza como parametro (:p); nunca se concatena.
"""
from __future__ import annotations

DETAIL = {}

DETAIL["identidad"] = """
SELECT b.batch_code, b.batch_type, b.status, p.sku, p.name AS producto,
       b.farm_name, b.municipality_name, b.harvest_year, b.harvest_period,
       b.received_date, b.production_date, b.expiry_date,
       b.cupping_score, b.humidity_pct, b.defect_pct,
       b.initial_quantity, u.code AS unidad, b.unit_cost, b.currency,
       ROUND(b.initial_quantity * b.unit_cost, 2) AS valor_inicial,
       po.order_number, po.status AS estado_orden
FROM batches b
JOIN products p ON p.id = b.product_id
JOIN units_of_measure u ON u.id = b.unit_id
LEFT JOIN production_orders po ON po.id = b.production_order_id
WHERE b.batch_code = :p
"""
DETAIL["padres"] = """
SELECT pb.batch_code AS lote_padre, pp.name AS producto, pb.farm_name, pb.municipality_name, pb.harvest_year,
       bl.quantity_consumed, ul.code AS unidad_consumo, bl.contribution_pct,
       pb.unit_cost AS costo_unitario_padre, up.code AS unidad_costo_padre,
       CASE WHEN bl.unit_id = pb.unit_id THEN ROUND(bl.quantity_consumed * pb.unit_cost, 2) END AS costo_consumido
FROM batch_lineage bl
JOIN batches b  ON b.id = bl.child_batch_id AND b.batch_code = :p
JOIN batches pb ON pb.id = bl.parent_batch_id
JOIN products pp ON pp.id = pb.product_id
JOIN units_of_measure ul ON ul.id = bl.unit_id
JOIN units_of_measure up ON up.id = pb.unit_id
ORDER BY bl.contribution_pct DESC, pb.batch_code
"""
DETAIL["hijos"] = """
SELECT cb.batch_code AS lote_hijo, cp.name AS producto, bl.quantity_consumed,
       ul.code AS unidad_consumo, bl.contribution_pct
FROM batch_lineage bl
JOIN batches b  ON b.id = bl.parent_batch_id AND b.batch_code = :p
JOIN batches cb ON cb.id = bl.child_batch_id
JOIN products cp ON cp.id = cb.product_id
JOIN units_of_measure ul ON ul.id = bl.unit_id
ORDER BY cb.batch_code
"""
DETAIL["orden"] = """
SELECT po.order_number, po.status, po.started_at, po.completed_at,
       po.total_input_cost, po.total_process_cost, po.total_overhead_cost, po.total_cost,
       po.output_quantity_base, po.waste_quantity_base, po.yield_pct, po.unit_cost
FROM production_orders po
JOIN batches b ON b.production_order_id = po.id AND b.batch_code = :p
"""
DETAIL["ejecuciones"] = """
SELECT pe.sequence_no, pr.name AS proceso, pe.executor_type,
       ex.legal_name AS ejecutor, pe.status,
       pe.input_quantity_base, pe.output_quantity_base, pe.waste_quantity_base, pe.yield_pct,
       pe.computed_cost, pe.actual_cost,
       CASE WHEN pe.actual_cost IS NOT NULL THEN pe.actual_cost - pe.computed_cost END AS desviacion,
       COALESCE(pe.actual_cost, pe.computed_cost) AS costo_efectivo
FROM process_executions pe
JOIN batches b ON b.production_order_id = pe.production_order_id AND b.batch_code = :p
JOIN production_processes pr ON pr.id = pe.process_id
LEFT JOIN parties ex ON ex.id = pe.executor_party_id
ORDER BY pe.sequence_no
"""
DETAIL["costos_adicionales"] = """
SELECT pc.cost_type, COUNT(*) AS registros, SUM(pc.amount) AS monto
FROM production_costs pc
JOIN batches b ON b.production_order_id = pc.production_order_id AND b.batch_code = :p
GROUP BY pc.cost_type
ORDER BY monto DESC
"""
DETAIL["insumos"] = """
SELECT p.product_kind, p.name AS producto, ib.batch_code AS lote_insumo,
       SUM(pi.quantity_base) AS cantidad_base, SUM(pi.total_cost) AS costo_total
FROM production_inputs pi
JOIN batches b ON b.production_order_id = pi.production_order_id AND b.batch_code = :p
JOIN products p ON p.id = pi.product_id
LEFT JOIN batches ib ON ib.id = pi.batch_id
GROUP BY p.product_kind, p.name, ib.batch_code
ORDER BY costo_total DESC
"""
DETAIL["libro"] = """
SELECT cc.code AS categoria, cc.name, cc.affects_inventory,
       SUM(ce.amount) AS monto,
       SUM(CASE WHEN ce.is_estimated THEN 1 ELSE 0 END) AS registros_estimados,
       COUNT(*) AS registros
FROM cost_entries ce
JOIN cost_categories cc ON cc.id = ce.cost_category_id
JOIN batches b ON b.batch_code = :p
WHERE (ce.cost_object_type = 'BATCH' AND ce.cost_object_id = b.id)
   OR (ce.cost_object_type = 'PRODUCTION_ORDER' AND ce.cost_object_id = b.production_order_id)
GROUP BY cc.code, cc.name, cc.affects_inventory
ORDER BY monto DESC
"""
_SALES_CTES = """b AS (SELECT id FROM batches WHERE batch_code = :p),
lot_lines AS (
  SELECT sib.sale_item_id, SUM(sib.quantity_base) AS lot_qty, SUM(sib.total_cost) AS lot_cost
  FROM sale_item_batches sib JOIN b ON b.id = sib.batch_id
  GROUP BY sib.sale_item_id
),
lines AS (
  SELECT si.sale_id, si.id AS sale_item_id, ll.lot_qty, ll.lot_cost,
         ll.lot_qty / si.quantity_base AS share, si.subtotal, si.tax_amount
  FROM lot_lines ll JOIN sale_items si ON si.id = ll.sale_item_id
),
sale_lot AS (
  SELECT s.id AS sale_id, s.sale_number, s.sale_date, s.status, s.payment_status, s.channel,
         s.party_id, s.total AS sale_total, s.paid_amount AS sale_paid, s.due_date,
         SUM(l.lot_qty) AS qty, SUM(l.subtotal * l.share) AS revenue,
         SUM(l.tax_amount * l.share) AS tax, SUM(l.lot_cost) AS cogs
  FROM lines l JOIN sales s ON s.id = l.sale_id
  WHERE s.status IN ('CONFIRMED','DISPATCHED','DELIVERED')
  GROUP BY s.id
)"""
DETAIL["ventas"] = "WITH " + _SALES_CTES + """
SELECT sl.sale_number, sl.sale_date, sl.status, sl.payment_status, sl.channel,
       pt.legal_name AS cliente, sl.qty AS cantidad_base,
       ROUND(sl.revenue, 2) AS ingreso_neto, ROUND(sl.tax, 2) AS impuesto, ROUND(sl.cogs, 2) AS costo_ventas,
       ROUND(sl.revenue - sl.cogs, 2) AS margen,
       ROUND((sl.revenue - sl.cogs) / NULLIF(sl.revenue, 0), 4) AS margen_pct,
       ROUND(sl.sale_paid * (sl.revenue + sl.tax) / NULLIF(sl.sale_total, 0), 2) AS cobrado_atribuido,
       ROUND((sl.revenue + sl.tax) - sl.sale_paid * (sl.revenue + sl.tax) / NULLIF(sl.sale_total, 0), 2) AS por_cobrar_atribuido,
       sl.due_date
FROM sale_lot sl
JOIN parties pt ON pt.id = sl.party_id
ORDER BY sl.sale_date, sl.sale_number
"""
DETAIL["inventario"] = """
SELECT l.code AS ubicacion, l.location_type, ib.quantity_base, ib.average_unit_cost, ib.total_value,
       (SELECT SUM(m.direction * m.quantity_base) FROM inventory_movements m
         WHERE m.batch_id = b.id AND m.location_id = ib.location_id) AS saldo_segun_libro
FROM inventory_balances ib
JOIN batches b ON b.id = ib.batch_id AND b.batch_code = :p
JOIN inventory_locations l ON l.id = ib.location_id
ORDER BY l.code
"""
DETAIL["controles"] = """
WITH b AS (SELECT id, production_order_id FROM batches WHERE batch_code = :p),
descuadre AS (SELECT COUNT(*) AS n FROM (
           SELECT si.id FROM sale_items si
           JOIN sale_item_batches sib ON sib.sale_item_id = si.id
           WHERE si.id IN (SELECT s2.sale_item_id FROM sale_item_batches s2 JOIN b ON b.id = s2.batch_id)
           GROUP BY si.id, si.quantity_base
           HAVING ABS(SUM(sib.quantity_base) - si.quantity_base) > 0.0001) x),
excl AS (SELECT COUNT(DISTINCT s.id) AS n FROM sale_item_batches sib JOIN b ON b.id = sib.batch_id
           JOIN sale_items si ON si.id = sib.sale_item_id JOIN sales s ON s.id = si.sale_id
           WHERE s.status IN ('DRAFT','CANCELLED','RETURNED')),
neg AS (SELECT COUNT(*) AS n FROM inventory_balances ib JOIN b ON b.id = ib.batch_id WHERE ib.quantity_base < 0)
SELECT 'Ventas: lineas con lotes asignados descuadrados' AS control,
       CASE WHEN (SELECT n FROM descuadre) = 0 THEN 'OK' ELSE 'REVISAR' END AS estado,
       'lineas: ' || (SELECT n FROM descuadre) AS detalle
UNION ALL SELECT 'Ventas del lote excluidas del informe (borrador, cancelada, devuelta)',
       CASE WHEN (SELECT n FROM excl) = 0 THEN 'OK' ELSE 'INFORMATIVO' END, 'ventas: ' || (SELECT n FROM excl)
UNION ALL SELECT 'Saldos de inventario negativos',
       CASE WHEN (SELECT n FROM neg) = 0 THEN 'OK' ELSE 'REVISAR' END, 'saldos: ' || (SELECT n FROM neg)
"""

_LOTS = """
WITH sold AS (
  SELECT sib.batch_id,
         COUNT(DISTINCT s.id) AS sales_count,
         SUM(sib.quantity_base) AS qty_sold,
         SUM(sib.total_cost) AS cogs,
         SUM(si.subtotal * sib.quantity_base / si.quantity_base) AS revenue,
         SUM((si.subtotal + si.tax_amount) * sib.quantity_base / si.quantity_base
             * (s.total - s.paid_amount) / NULLIF(s.total, 0)) AS receivable,
         MAX(s.sale_date) AS last_sale
  FROM sale_item_batches sib
  JOIN sale_items si ON si.id = sib.sale_item_id
  JOIN sales s ON s.id = si.sale_id
  WHERE s.status IN ('CONFIRMED','DISPATCHED','DELIVERED')
  GROUP BY sib.batch_id
),
lots AS (
  SELECT b.id, b.batch_code, b.batch_type, b.status, b.production_date,
         b.initial_quantity, u.code AS unit, b.unit_cost,
         b.initial_quantity * b.unit_cost AS lot_cost,
         p.name AS product, po.order_number,
         COALESCE(x.sales_count, 0) AS sales_count, COALESCE(x.qty_sold, 0) AS qty_sold,
         COALESCE(x.revenue, 0) AS revenue, COALESCE(x.cogs, 0) AS cogs,
         COALESCE(x.receivable, 0) AS receivable, x.last_sale
  FROM batches b
  JOIN products p ON p.id = b.product_id
  JOIN units_of_measure u ON u.id = b.unit_id
  LEFT JOIN production_orders po ON po.id = b.production_order_id
  LEFT JOIN sold x ON x.batch_id = b.id
  WHERE (:ltype = '' OR b.batch_type = :ltype)
    AND (:lstatus = '' OR b.status = :lstatus)
    AND (:q = '' OR LOWER(b.batch_code) LIKE :q ESCAPE '\\' OR LOWER(p.name) LIKE :q ESCAPE '\\')
)
"""
SORTS = {
    "recent": "production_date IS NULL, production_date DESC, id DESC",
    "revenue": "revenue DESC, id DESC",
    "sell": "(CASE WHEN initial_quantity > 0 THEN qty_sold / initial_quantity ELSE 0 END) ASC, id DESC",
    "receivable": "receivable DESC, id DESC",
    "cost": "lot_cost DESC, id DESC",
}
LOT_SUMMARY = _LOTS + """
SELECT COUNT(*) AS lots,
       COALESCE(SUM(CASE WHEN sales_count > 0 THEN 1 ELSE 0 END), 0) AS with_sales,
       COALESCE(SUM(CASE WHEN status = 'ACTIVE' THEN 1 ELSE 0 END), 0) AS active,
       COALESCE(SUM(lot_cost), 0) AS lot_cost, COALESCE(SUM(revenue), 0) AS revenue,
       COALESCE(SUM(cogs), 0) AS cogs, COALESCE(SUM(receivable), 0) AS receivable
FROM lots
"""
LOT_TYPE_COUNTS = "SELECT batch_type, COUNT(*) AS n FROM batches GROUP BY batch_type"


def lot_page_sql(sort: str) -> str:
    order = SORTS.get(sort, SORTS["recent"])  # lista blanca: nunca se interpola texto del usuario
    return _LOTS + "SELECT * FROM lots ORDER BY " + order + " LIMIT :limit OFFSET :offset"


def _like(text: str) -> str:
    text = text.strip().lower()
    if not text:
        return ""
    return "%" + text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"


def list_lots(execute, filters: dict, page_size: int = 12) -> dict:
    params = {"ltype": filters["type"], "lstatus": filters["status"], "q": _like(filters["q"])}
    summary = execute(LOT_SUMMARY, params)[0]
    total = int(summary["lots"] or 0)
    pages = max(1, -(-total // page_size))
    page = min(max(1, filters["page"]), pages)
    rows = execute(lot_page_sql(filters["sort"]), {**params, "limit": page_size, "offset": (page - 1) * page_size})
    counts = {r["batch_type"]: int(r["n"]) for r in execute(LOT_TYPE_COUNTS, {})}
    return {"summary": summary, "rows": rows, "page": page, "pages": pages, "type_counts": counts}


def fetch_report(execute, code: str) -> dict:
    return {key: execute(sql, {"p": code}) for key, sql in DETAIL.items()}
