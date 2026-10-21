#!/usr/bin/env python3
"""Informe administrativo y financiero de un lote · Densa Niebla  (SOLO LECTURA)

Genera un tablero HTML autocontenido (+ una copia JSON para reconstruirlo despues)
para CUALQUIER lote, pasado o futuro, a partir de su codigo.

  python informe_lote.py DN-CAST-MOL26-1                 # usa DATABASE_URL (entorno o .env)
  python informe_lote.py DN-CAST-MOL26-1 --dsn postgresql://usuario:clave@host:5432/base
  python informe_lote.py --list                          # ultimos lotes y sus codigos
  python informe_lote.py --from-json informes/informe_DN-CAST-MOL26-1.json   # sin base de datos

Seguridad: la sesion se abre en modo SOLO LECTURA (PostgreSQL rechaza cualquier escritura),
las consultas son SELECT y no se guarda la cadena de conexion en el resultado.
Dependencias: psycopg2 o psycopg (v3). Nada mas.
"""
from __future__ import annotations

import argparse
import datetime as dt
import decimal
import json
import os
import re
import sys
from pathlib import Path

QUERIES = {
    "identidad": """
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
WHERE b.batch_code = {{BATCH}}
""",
    "padres": """
SELECT pb.batch_code AS lote_padre, pp.name AS producto, pb.farm_name, pb.municipality_name, pb.harvest_year,
       bl.quantity_consumed, ul.code AS unidad_consumo, bl.contribution_pct,
       pb.unit_cost AS costo_unitario_padre, up.code AS unidad_costo_padre,
       CASE WHEN bl.unit_id = pb.unit_id THEN ROUND(bl.quantity_consumed * pb.unit_cost, 2) END AS costo_consumido
FROM batch_lineage bl
JOIN batches b  ON b.id = bl.child_batch_id AND b.batch_code = {{BATCH}}
JOIN batches pb ON pb.id = bl.parent_batch_id
JOIN products pp ON pp.id = pb.product_id
JOIN units_of_measure ul ON ul.id = bl.unit_id
JOIN units_of_measure up ON up.id = pb.unit_id
ORDER BY bl.contribution_pct DESC, pb.batch_code
""",
    "hijos": """
SELECT cb.batch_code AS lote_hijo, cp.name AS producto, bl.quantity_consumed,
       ul.code AS unidad_consumo, bl.contribution_pct
FROM batch_lineage bl
JOIN batches b  ON b.id = bl.parent_batch_id AND b.batch_code = {{BATCH}}
JOIN batches cb ON cb.id = bl.child_batch_id
JOIN products cp ON cp.id = cb.product_id
JOIN units_of_measure ul ON ul.id = bl.unit_id
ORDER BY cb.batch_code
""",
    "orden": """
SELECT po.order_number, po.status, po.started_at, po.completed_at,
       po.total_input_cost, po.total_process_cost, po.total_overhead_cost, po.total_cost,
       po.output_quantity_base, po.waste_quantity_base, po.yield_pct, po.unit_cost
FROM production_orders po
JOIN batches b ON b.production_order_id = po.id AND b.batch_code = {{BATCH}}
""",
    "ejecuciones": """
SELECT pe.sequence_no, pr.name AS proceso, pe.executor_type,
       ex.legal_name AS ejecutor, pe.status,
       pe.input_quantity_base, pe.output_quantity_base, pe.waste_quantity_base, pe.yield_pct,
       pe.computed_cost, pe.actual_cost,
       CASE WHEN pe.actual_cost IS NOT NULL THEN pe.actual_cost - pe.computed_cost END AS desviacion,
       COALESCE(pe.actual_cost, pe.computed_cost) AS costo_efectivo
FROM process_executions pe
JOIN batches b ON b.production_order_id = pe.production_order_id AND b.batch_code = {{BATCH}}
JOIN production_processes pr ON pr.id = pe.process_id
LEFT JOIN parties ex ON ex.id = pe.executor_party_id
ORDER BY pe.sequence_no
""",
    "costos_adicionales": """
SELECT pc.cost_type, COUNT(*) AS registros, SUM(pc.amount) AS monto
FROM production_costs pc
JOIN batches b ON b.production_order_id = pc.production_order_id AND b.batch_code = {{BATCH}}
GROUP BY pc.cost_type
ORDER BY monto DESC
""",
    "insumos": """
SELECT p.product_kind, p.name AS producto, ib.batch_code AS lote_insumo,
       SUM(pi.quantity_base) AS cantidad_base, SUM(pi.total_cost) AS costo_total
FROM production_inputs pi
JOIN batches b ON b.production_order_id = pi.production_order_id AND b.batch_code = {{BATCH}}
JOIN products p ON p.id = pi.product_id
LEFT JOIN batches ib ON ib.id = pi.batch_id
GROUP BY p.product_kind, p.name, ib.batch_code
ORDER BY costo_total DESC
""",
    "libro": """
SELECT cc.code AS categoria, cc.name, cc.affects_inventory,
       SUM(ce.amount) AS monto,
       SUM(CASE WHEN ce.is_estimated THEN 1 ELSE 0 END) AS registros_estimados,
       COUNT(*) AS registros
FROM cost_entries ce
JOIN cost_categories cc ON cc.id = ce.cost_category_id
JOIN batches b ON b.batch_code = {{BATCH}}
WHERE (ce.cost_object_type = 'BATCH' AND ce.cost_object_id = b.id)
   OR (ce.cost_object_type = 'PRODUCTION_ORDER' AND ce.cost_object_id = b.production_order_id)
GROUP BY cc.code, cc.name, cc.affects_inventory
ORDER BY monto DESC
""",
    "ventas": """WITH b AS (SELECT id FROM batches WHERE batch_code = {{BATCH}}),
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
)
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
""",
    "inventario": """
SELECT l.code AS ubicacion, l.location_type, ib.quantity_base, ib.average_unit_cost, ib.total_value,
       (SELECT SUM(m.direction * m.quantity_base) FROM inventory_movements m
         WHERE m.batch_id = b.id AND m.location_id = ib.location_id) AS saldo_segun_libro
FROM inventory_balances ib
JOIN batches b ON b.id = ib.batch_id AND b.batch_code = {{BATCH}}
JOIN inventory_locations l ON l.id = ib.location_id
ORDER BY l.code
""",
    "controles": """
WITH b AS (SELECT id, production_order_id FROM batches WHERE batch_code = {{BATCH}}),
lin AS (SELECT SUM(bl.contribution_pct) AS suma, COUNT(*) AS padres
        FROM batch_lineage bl JOIN b ON b.id = bl.child_batch_id),
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
SELECT 'Linaje: suma de aportes de los padres = 100 %' AS control,
       CASE WHEN (SELECT padres FROM lin) = 0 THEN 'NO APLICA' WHEN ABS((SELECT suma FROM lin) - 1) <= 0.0001 THEN 'OK' ELSE 'REVISAR' END AS estado,
       'padres: ' || (SELECT padres FROM lin) AS detalle
UNION ALL SELECT 'Ventas: lineas con lotes asignados descuadrados',
       CASE WHEN (SELECT n FROM descuadre) = 0 THEN 'OK' ELSE 'REVISAR' END, 'lineas: ' || (SELECT n FROM descuadre)
UNION ALL SELECT 'Ventas del lote excluidas del informe (borrador, cancelada, devuelta)',
       CASE WHEN (SELECT n FROM excl) = 0 THEN 'OK' ELSE 'INFORMATIVO' END, 'ventas: ' || (SELECT n FROM excl)
UNION ALL SELECT 'Saldos de inventario negativos',
       CASE WHEN (SELECT n FROM neg) = 0 THEN 'OK' ELSE 'REVISAR' END, 'saldos: ' || (SELECT n FROM neg)
""",
}

LIST_SQL = """
SELECT b.batch_code, b.batch_type, b.status, b.production_date, p.name AS producto
FROM batches b JOIN products p ON p.id = b.product_id
ORDER BY b.id DESC LIMIT 40
"""

TEMPLATE = r"""<!doctype html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="robots" content="noindex,nofollow">
<title>Informe de lote · Densa Niebla</title>
<style>
:root{--forest:#14382d;--forest-deep:#0c271f;--forest-hover:#1b4638;--paper:#fbfaf4;--cream:#f3efe5;--copper:#b47755;--ink:#213229;--muted:#6d796f;--line:#d4d6cc;--field:#fffefa;--sage:#5da677;--gold:#d8bd77;--terra:#a0443c;--ok-fg:#1d5d3f;--ok-bg:#e3f1e8;--warn-fg:#72551d;--warn-bg:#f7eed5;--info-fg:#1e5973;--info-bg:#e4f0f5;--bad-fg:#903e37;--bad-bg:#f9e6e3;--serif:Georgia,"Times New Roman",serif;--sans:Inter,ui-sans-serif,system-ui,-apple-system,"Segoe UI",sans-serif;--shadow:0 16px 44px rgba(18,47,38,.09)}
*{box-sizing:border-box}
body{margin:0;color:var(--ink);font:400 .875rem/1.5 var(--sans);background:radial-gradient(circle at 92% -5%,rgba(180,119,85,.10),transparent 28rem),var(--paper);min-height:100vh}
h1,h2,h3{margin:0;color:var(--forest);font-family:var(--serif);font-weight:600}
p{margin:0}
.topbar{position:sticky;top:0;z-index:20;display:flex;align-items:center;justify-content:space-between;gap:16px;min-height:66px;padding:0 clamp(16px,4vw,52px);background:rgba(251,250,244,.94);border-bottom:1px solid #deded3;backdrop-filter:blur(13px)}
.brand{display:flex;align-items:center;gap:10px;color:var(--forest)}
.mark{display:grid;place-items:center;width:38px;height:38px;border-radius:12px;background:var(--forest);color:var(--gold);font:700 .8rem var(--serif)}
.brand strong{display:block;font:600 1.03rem var(--serif);letter-spacing:-.015em}
.brand span{display:block;margin-top:2px;color:var(--muted);font-size:.57rem;font-weight:800;letter-spacing:.11em;text-transform:uppercase}
.actions{display:flex;gap:9px;flex-wrap:wrap}
.btn{display:inline-flex;align-items:center;justify-content:center;min-height:44px;padding:10px 15px;color:var(--forest);background:var(--paper);border:1px solid var(--forest);border-radius:9px;font:700 .8rem var(--sans);cursor:pointer}
.btn:hover{background:var(--cream)}
.btn:focus-visible,.scroll:focus-visible{outline:2px solid var(--copper);outline-offset:3px}
.wrap{width:min(1280px,100%);margin:0 auto;padding:24px clamp(16px,4vw,52px) 64px}
.crumbs{display:flex;flex-wrap:wrap;gap:7px;margin-bottom:7px;color:var(--muted);font-size:.7rem;font-weight:700}
.kicker{margin:0 0 6px;color:var(--copper);font-size:.66rem;font-weight:850;letter-spacing:.13em;text-transform:uppercase}
.head{display:flex;justify-content:space-between;align-items:end;gap:20px;flex-wrap:wrap;margin-bottom:22px}
.head h1{font-size:clamp(1.65rem,3.2vw,2.55rem);letter-spacing:-.03em;line-height:1.1;overflow-wrap:anywhere}
.head p.lead{max-width:760px;margin-top:7px;color:var(--muted);font-size:.86rem;line-height:1.55}
.chips{display:flex;flex-wrap:wrap;gap:7px;margin-top:12px}
.pill{display:inline-flex;align-items:center;min-height:27px;padding:5px 9px;border-radius:999px;font-size:.66rem;font-weight:850;letter-spacing:.06em;text-transform:uppercase;white-space:nowrap}
.ok{color:var(--ok-fg);background:var(--ok-bg)}.warn{color:var(--warn-fg);background:var(--warn-bg)}.info{color:var(--info-fg);background:var(--info-bg)}.bad{color:var(--bad-fg);background:var(--bad-bg)}.soft{color:var(--forest);background:var(--cream)}.na{color:var(--muted);background:#ecece4}
.cut{padding-left:20px;border-left:2px solid var(--copper);color:var(--muted);font-size:.72rem;line-height:1.5}
.cut strong{display:block;color:var(--forest);font:600 1rem var(--serif)}
.kpis{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:13px;margin-bottom:22px}
.card{background:rgba(255,253,248,.94);border:1px solid rgba(29,65,53,.11);border-radius:18px;box-shadow:var(--shadow);min-width:0;overflow:hidden}
.kpi{display:grid;gap:6px;min-height:136px;padding:18px}
.lbl{color:var(--muted);font-size:.67rem;font-weight:800;letter-spacing:.1em;text-transform:uppercase}
.kpi strong{color:var(--forest);font:600 clamp(1.4rem,2.3vw,2rem)/1 var(--serif);overflow-wrap:anywhere}
.kpi small{align-self:end;color:var(--muted);font-size:.72rem;line-height:1.4}
.grid{display:grid;grid-template-columns:repeat(12,minmax(0,1fr));gap:18px;margin-bottom:18px}
.s5{grid-column:span 5}.s6{grid-column:span 6}.s7{grid-column:span 7}.s12{grid-column:1/-1}
@media(max-width:980px){.s5,.s6,.s7{grid-column:1/-1}}
.ph{display:flex;justify-content:space-between;align-items:center;gap:14px;flex-wrap:wrap;padding:18px 22px;border-bottom:1px solid var(--line)}
.ph h2{font-size:1.25rem;line-height:1.25;margin-top:3px}
.pb{padding:20px 22px}
.dark{background:var(--forest);border-color:var(--forest);color:#fff}
.dark .ph{border-color:rgba(255,255,255,.17)}.dark h2,.dark strong{color:#fff}.dark .kicker{color:#dfb89f}.dark .lbl,.dark small,.dark .muted{color:rgba(255,255,255,.66)}
.muted{color:var(--muted);font-size:.76rem}
.big{font:600 clamp(1.7rem,3vw,2.3rem)/1.05 var(--serif)}
.bar{display:flex;height:16px;border-radius:999px;overflow:hidden;background:rgba(0,0,0,.08);margin:14px 0}
.bar i{display:block;height:100%}
.legend{display:grid;gap:0}
.legend .row{display:grid;grid-template-columns:12px minmax(0,1fr) auto auto;gap:10px;align-items:center;padding:9px 0;border-top:1px solid rgba(255,255,255,.17);font-size:.8rem}
.legend .row:first-child{border-top:0}
.dot{width:10px;height:10px;border-radius:50%}
.num{text-align:right;white-space:nowrap;font-variant-numeric:tabular-nums}
.hb{display:grid;gap:12px}
.hb .it{display:grid;gap:5px}
.hb .top{display:flex;justify-content:space-between;gap:10px;font-size:.8rem}
.track{height:12px;border-radius:999px;background:var(--cream);overflow:hidden}
.track i{display:block;height:100%;border-radius:999px;transform-origin:left}
.tw{overflow-x:auto}
table{width:100%;border-collapse:collapse;min-width:640px}
th,td{padding:12px 14px;text-align:left;vertical-align:middle;border-bottom:1px solid var(--line);font-size:.8rem}
th{color:var(--muted);font-size:.64rem;font-weight:800;letter-spacing:.08em;text-transform:uppercase}
td.r,th.r{text-align:right}
tbody tr:last-child td{border-bottom:0}
td strong{color:var(--forest)}
.nw{white-space:nowrap}
.list{display:grid;gap:0;margin:0;padding:0;list-style:none}
.list li{display:grid;grid-template-columns:auto minmax(0,1fr);gap:12px;padding:12px 0;border-top:1px solid var(--line);align-items:start}
.list li:first-child{border-top:0;padding-top:0}
.list p{font-size:.82rem;line-height:1.5}.list .muted{display:block;margin-top:2px}
.chain{display:flex;flex-wrap:wrap;align-items:stretch;gap:10px}
.node{flex:1 1 150px;min-width:140px;padding:13px;border:1px solid var(--line);border-radius:12px;background:var(--paper)}
.node b{display:block;color:var(--forest);font:600 .95rem var(--serif);overflow-wrap:anywhere}
.node small{display:block;margin-top:3px;color:var(--muted);font-size:.7rem;line-height:1.4}
.node.gap{border-style:dashed;border-color:var(--terra)}
.arrow{align-self:center;color:var(--copper);font-size:1.1rem}
.stat3{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:12px;margin-top:16px}
.stat3 div{padding-top:12px;border-top:1px solid var(--line)}
.stat3 strong{display:block;margin-top:4px;color:var(--forest);font:600 1.1rem var(--serif)}
.note{margin-top:14px;padding:13px 15px;border:1px solid var(--line);border-radius:10px;background:var(--cream);font-size:.78rem;line-height:1.5}
svg text{font-family:var(--sans)}
.mask .pii{filter:blur(5px);user-select:none}
.foot{margin-top:26px;color:var(--muted);font-size:.72rem;line-height:1.55}
.sr{position:absolute;width:1px;height:1px;margin:-1px;overflow:hidden;clip:rect(0,0,0,0);white-space:nowrap}
@media(max-width:620px){.head{align-items:stretch}.stat3{grid-template-columns:1fr}.pb,.ph{padding:16px}}
@media print{.topbar .actions{display:none}.topbar{position:static}body{background:#fff}.card{box-shadow:none;break-inside:avoid}}
</style>
</head>
<body>
<header class="topbar">
  <div class="brand"><div class="mark" aria-hidden="true">DN</div><div><strong>Densa Niebla</strong><span>Informe de lote</span></div></div>
  <div class="actions">
    <button class="btn" type="button" id="btn-mask" aria-pressed="false">Ocultar nombres de clientes</button>
    <button class="btn" type="button" id="btn-print">Imprimir / PDF</button>
  </div>
</header>
<main class="wrap" id="app" aria-live="polite"></main>
<script src="https://cdn.jsdelivr.net/npm/gsap@3.14.1/dist/gsap.min.js" defer></script>
<script>
const D = /*__DATA__*/null;

(() => {
'use strict';
const esc = s => String(s == null ? '' : s).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const num = v => (v == null || v === '' || isNaN(+v)) ? 0 : +v;
const sum = (a, f) => (a || []).reduce((s, x) => s + num(x[f]), 0);
const nf = (d) => new Intl.NumberFormat('es-CO', {minimumFractionDigits: d, maximumFractionDigits: d});
const money = (v, d = 0) => v == null || isNaN(v) ? '—' : '$ ' + nf(d).format(v);
const qty = (v, d = 2) => v == null || isNaN(v) ? '—' : nf(Number.isInteger(+v) ? 0 : d).format(v);
const pct = (v, d = 1) => v == null || !isFinite(v) ? '—' : nf(d).format(v * 100) + ' %';
const dstr = iso => { if (!iso) return '—'; const m = String(iso).match(/^(\d{4})-(\d{2})-(\d{2})/); return m ? `${m[3]}/${m[2]}/${m[1]}` : esc(iso); };
const dval = iso => { const m = String(iso || '').match(/^(\d{4})-(\d{2})-(\d{2})/); return m ? Date.UTC(+m[1], +m[2] - 1, +m[3]) : null; };
const dayDiff = (a, b) => Math.round((dval(a) - dval(b)) / 86400000);
const has = a => Array.isArray(a) && a.length > 0;
const letters = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ';
const state = {mask: false, first: true};

function derive(D) {
  const lot = has(D.identidad) ? D.identidad[0] : null;
  if (!lot) return null;
  const cutoff = (D.meta && D.meta.cutoff) || new Date().toISOString().slice(0, 10);
  const ventas = D.ventas || [];
  const padres = D.padres || [], hijos = D.hijos || [], ejec = D.ejecuciones || [], ins = D.insumos || [], adic = D.costos_adicionales || [];
  const o = has(D.orden) ? D.orden[0] : null;
  const initial = num(lot.initial_quantity), unitCost = num(lot.unit_cost);
  const lotCost = num(lot.valor_inicial) || initial * unitCost;
  const q = sum(ventas, 'cantidad_base'), rev = sum(ventas, 'ingreso_neto'), tax = sum(ventas, 'impuesto'), cogs = sum(ventas, 'costo_ventas');
  const paid = sum(ventas, 'cobrado_atribuido'), due = sum(ventas, 'por_cobrar_atribuido');
  const avgPrice = q > 0 ? rev / q : null, avgCost = q > 0 ? cogs / q : null;
  const margin = rev - cogs, marginPct = rev > 0 ? margin / rev : null;
  const sellThrough = initial > 0 ? q / initial : null;
  const breakeven = avgPrice > 0 ? Math.ceil(lotCost / avgPrice) : null;
  const potRev = avgPrice != null ? initial * avgPrice : null;
  const invAvail = has(D.inventario);
  const remainingTheo = initial - q;
  const remainingReal = invAvail ? sum(D.inventario, 'quantity_base') : null;
  const remaining = remainingReal != null ? remainingReal : remainingTheo;
  const invValue = invAvail ? sum(D.inventario, 'total_value') : remaining * unitCost;

  let comp = null;
  if (o) {
    const raw = sum(ins.filter(x => x.product_kind === 'RAW_MATERIAL'), 'costo_total');
    const sup = sum(ins.filter(x => x.product_kind === 'SUPPLY'), 'costo_total');
    const oth = Math.max(0, num(o.total_input_cost) - raw - sup);
    const share = num(o.total_cost) > 0 ? Math.min(1, lotCost / num(o.total_cost)) : null;
    const rows = [
      {k: 'Materia prima (café)', v: raw, c: 'var(--gold)'},
      {k: 'Empaque e insumos', v: sup, c: 'var(--sage)'},
      {k: 'Otros insumos', v: oth, c: '#b9c2b8'},
      {k: 'Proceso / maquila', v: num(o.total_process_cost), c: 'var(--copper)'},
      {k: 'Estructura / transporte', v: num(o.total_overhead_cost), c: '#ffffff'}
    ].filter(x => x.v > 0.005);
    comp = {rows, share, total: num(o.total_cost), sumRows: rows.reduce((s, x) => s + x.v, 0)};
  }
  const overdue = ventas.filter(v => num(v.por_cobrar_atribuido) > 0.005 && v.due_date && dayDiff(cutoff, v.due_date) > 0)
    .map(v => ({...v, days: dayDiff(cutoff, v.due_date)}));
  const overdueAmt = sum(overdue, 'por_cobrar_atribuido');
  const buckets = [['Vence hoy o después', 0], ['1 a 30 días', 0], ['31 a 60 días', 0], ['Más de 60 días', 0]];
  ventas.forEach(v => {
    const a = num(v.por_cobrar_atribuido); if (a <= 0.005) return;
    const d = v.due_date ? dayDiff(cutoff, v.due_date) : 0;
    buckets[d <= 0 ? 0 : d <= 30 ? 1 : d <= 60 ? 2 : 3][1] += a;
  });
  return {lot, o, cutoff, ventas, padres, hijos, ejec, ins, adic, initial, unitCost, lotCost, q, rev, tax, cogs, paid, due, avgPrice, avgCost, margin,
    marginPct, sellThrough, breakeven, potRev, invAvail, remaining, remainingTheo, remainingReal, invValue, comp, overdue, overdueAmt, buckets};
}

function controls(D, m) {
  const c = [];
  const add = (name, state, detail) => c.push({name, state, detail});
  const farm = m.lot.farm_name || m.padres.some(p => p.farm_name);
  add('Origen: finca registrada', farm ? 'OK' : 'REVISAR', farm ? 'El lote o sus padres tienen finca' : 'Ni el lote ni sus padres tienen finca, municipio o cosecha: se pierde la historia de origen');
  if (m.padres.length) {
    const s = sum(m.padres, 'contribution_pct');
    add('Linaje: aportes de padres suman 100 %', Math.abs(s - 1) <= 0.0015 ? 'OK' : 'INFO', `Suma ${pct(s, 2)}${s < 0.9985 ? ': el resto de la orden alimenta otros lotes' : ''}`);
  }
  if (m.o) {
    const parts = num(m.o.total_input_cost) + num(m.o.total_process_cost) + num(m.o.total_overhead_cost);
    add('Orden: café + proceso + estructura = costo total', Math.abs(parts - num(m.o.total_cost)) < 1 ? 'OK' : 'REVISAR', `Suma ${money(parts)} frente a ${money(num(m.o.total_cost))}`);
    if (m.ins.length) add('Orden: insumos detallados = costo de insumos', Math.abs(sum(m.ins, 'costo_total') - num(m.o.total_input_cost)) < 1 ? 'OK' : 'REVISAR', `Detalle ${money(sum(m.ins, 'costo_total'))} frente a ${money(num(m.o.total_input_cost))}`);
    if (m.ejec.length) add('Maquila: costo efectivo = costo de proceso de la orden', Math.abs(sum(m.ejec, 'costo_efectivo') - num(m.o.total_process_cost)) < 1 ? 'OK' : 'REVISAR', `Ejecuciones ${money(sum(m.ejec, 'costo_efectivo'))} frente a ${money(num(m.o.total_process_cost))}`);
    const ext = m.ejec.filter(e => e.executor_type === 'EXTERNAL' && e.actual_cost == null).length;
    if (m.ejec.length) add('Maquila externa con costo real facturado', ext ? 'REVISAR' : 'OK', ext ? `${ext} ejecución(es) con costo solo calculado` : 'Todo con costo real');
    if (m.comp && m.comp.share != null) add('Costo del lote ≤ costo de la orden', m.lotCost <= m.o.total_cost + 1 ? 'OK' : 'REVISAR', m.comp.share < 0.999 ? `El lote lleva ${pct(m.comp.share)} de la orden; el resto corresponde a otros lotes` : 'El lote lleva toda la orden');
    const dup = m.adic.find(a => Math.abs(num(a.monto) - num(m.o.total_process_cost)) < 1 && num(a.monto) > 0);
    if (dup) add('Costos adicionales vs. proceso', 'INFO', `El costo adicional "${dup.cost_type}" (${money(num(dup.monto))}) coincide con el proceso/maquila: es el mismo valor, no se suma dos veces`);
    add('Orden con costeo cerrado', m.o.status === 'CLOSED' ? 'OK' : 'REVISAR', `Estado de la orden: ${m.o.status}`);
    if (m.o.started_at && m.o.started_at === m.o.completed_at) add('Orden registrada con fechas reales', 'INFO', 'Inicio y fin son idénticos: parece una orden histórica o reconstruida');
  } else add('Orden de producción asociada', 'NA', 'El lote no tiene orden (p. ej. lote comprado)');
  const pre = m.lot.production_date ? m.ventas.filter(v => dval(v.sale_date) < dval(m.lot.production_date)) : [];
  if (m.lot.production_date) add('Ventas anteriores a la producción del lote', pre.length ? 'INFO' : 'OK', pre.length ? `${pre.length} de ${m.ventas.length} ventas tienen fecha previa al ${dstr(m.lot.production_date)} (preventa o fecha retroactiva)` : 'Ninguna');
  if (m.ventas.length) {
    add('Ventas sin cobro registrado', m.paid <= 0.005 ? 'INFO' : 'OK', m.paid <= 0.005 ? 'Cobrado atribuido = 0: confirma que los cobros se registraron en pagos' : `Cobrado ${money(m.paid)}`);
    add('Cartera vencida', m.overdue.length ? 'REVISAR' : 'OK', m.overdue.length ? `${m.overdue.length} venta(s) vencidas por ${money(m.overdueAmt)}; el estado de pago sigue como ${[...new Set(m.overdue.map(x => x.payment_status))].join('/')}` : 'Sin vencidas');
  }
  if (m.sellThrough != null && m.lot.status === 'ACTIVE') add('Ventas trazadas al lote vs. cantidad producida', m.sellThrough < 0.1 ? 'INFO' : 'OK', `Solo ${pct(m.sellThrough)} de las unidades del lote tiene venta asignada; si se vendió más, falta asignar lote a esas ventas`);
  if (m.invAvail) {
    const d = Math.abs(m.remainingReal - m.remainingTheo);
    add('Inventario real vs. teórico', d < 0.001 ? 'OK' : 'REVISAR', `Real ${qty(m.remainingReal)} frente a teórico ${qty(m.remainingTheo)} ${esc(m.lot.unidad)}`);
  } else add('Inventario real vs. teórico', 'NA', 'No hay saldos del lote en inventory_balances: el saldo mostrado es teórico (producido − vendido)');
  (D.controles || []).forEach(x => add(x.control, x.estado === 'OK' ? 'OK' : x.estado === 'NO APLICA' ? 'NA' : x.estado === 'INFORMATIVO' ? 'INFO' : 'REVISAR', x.detalle));
  return c;
}

const PILL = {OK: ['ok', 'OK'], REVISAR: ['bad', 'Revisar'], INFO: ['warn', 'Informativo'], NA: ['na', 'No aplica']};
const panel = (kicker, title, body, cls = '', dark = false) => `<section class="card reveal ${cls} ${dark ? 'dark' : ''}"><div class="ph"><div><p class="kicker">${esc(kicker)}</p><h2>${esc(title)}</h2></div></div><div class="pb">${body}</div></section>`;
const track = (v, max, color) => `<div class="track"><i class="fill" style="width:${max > 0 ? Math.max(0, Math.min(100, v / max * 100)) : 0}%;background:${color}"></i></div>`;

function render() {
  const app = document.getElementById('app');
  document.body.classList.toggle('mask', state.mask);
  const m = derive(D);
  if (!m) { app.innerHTML = '<p>No hay datos del lote.</p>'; return; }
  const L = m.lot, U = esc(L.unidad || '');
  const names = {}; let ni = 0; m.ventas.forEach(v => { if (!(v.cliente in names)) names[v.cliente] = 'Cliente ' + (letters[ni++ % 26]); });
  const who = n => `<span>${esc(state.mask ? names[n] : n)}</span>`;
  const ctr = controls(D, m);
  const bad = ctr.filter(x => x.state === 'REVISAR').length, info = ctr.filter(x => x.state === 'INFO').length;

  const head = `<div class="head reveal"><div><div class="crumbs"><span>ERP</span><span>›</span><span>Producción</span><span>›</span><span>Lotes</span><span>›</span><strong style="color:var(--forest)">${esc(L.batch_code)}</strong></div>
    <p class="kicker">Densa Niebla · Informe administrativo y financiero</p><h1>${esc(L.batch_code)}</h1>
    <p class="lead">${esc(L.producto)}${L.sku ? ' · ' + esc(L.sku) : ''}. ${L.production_date ? 'Producido el ' + dstr(L.production_date) + '.' : ''} ${L.order_number ? 'Orden ' + esc(L.order_number) + '.' : ''}</p>
    <div class="chips"><span class="pill soft">${esc(L.batch_type)}</span><span class="pill ${L.status === 'ACTIVE' ? 'ok' : 'warn'}">${esc(L.status)}</span>${L.estado_orden ? `<span class="pill info">Orden ${esc(L.estado_orden)}</span>` : ''}<span class="pill ${bad ? 'bad' : 'ok'}">${bad ? bad + ' por revisar' : 'Sin alertas críticas'}</span>${info ? `<span class="pill warn">${info} informativo(s)</span>` : ''}</div></div>
    <div class="cut">Corte de datos<strong>${dstr(m.cutoff)}</strong>Generado ${esc(((D.meta && D.meta.generated_at) || '').slice(0, 16).replace('T', ' '))}<br>Fuente: ${esc((D.meta && D.meta.source) || 'ERP')}</div></div>`;

  const kpi = (l, v, fmt, small) => `<div class="card kpi reveal"><span class="lbl">${l}</span><strong data-count="${v == null ? '' : v}" data-fmt="${fmt}">${fmtBy(fmt, v)}</strong><small>${small}</small></div>`;
  const kpis = `<div class="kpis">
    ${kpi('Ingreso neto vendido', m.rev, 'money', `${m.ventas.length} venta(s) · ${qty(m.q)} ${U} · sin IVA`)}
    ${kpi('Margen bruto', m.margin, 'money', `${pct(m.marginPct)} sobre lo vendido`)}
    ${kpi('Vendido del lote', m.sellThrough, 'pct', `${qty(m.q)} de ${qty(m.initial)} ${U}`)}
    ${kpi('Por cobrar', m.due, 'money', m.overdue.length ? `Vencido: ${money(m.overdueAmt)}` : 'Sin cartera vencida')}
    ${kpi('Costo recuperado', m.lotCost > 0 ? m.rev / m.lotCost : null, 'pct', `Costo del lote ${money(m.lotCost)}`)}
  </div>`;

  const facts = [];
  facts.push(`Se asignaron a ventas ${qty(m.q)} de ${qty(m.initial)} ${U} (${pct(m.sellThrough)}). Lo vendido deja ${money(m.rev)} de ingreso neto y ${money(m.margin)} de margen bruto (${pct(m.marginPct)}).`);
  if (m.avgPrice != null) facts.push(`Precio promedio ${money(m.avgPrice, 2)} frente a costo unitario ${money(m.avgCost, 2)} por ${U}: margen de ${money(m.avgPrice - m.avgCost, 2)} por unidad.`);
  if (m.breakeven != null) facts.push(m.q >= m.breakeven ? `El lote ya recuperó su costo (${money(m.lotCost)}).` : `Para recuperar el costo del lote hacen falta ${qty(m.breakeven)} ${U} al precio promedio; faltan ${qty(m.breakeven - m.q)}.`);
  if (m.potRev != null) facts.push(`Proyección, no resultado: si se vendiera todo el lote al precio promedio, el ingreso sería ${money(m.potRev)} y el margen ${money(m.potRev - m.lotCost)}.`);
  if (m.due > 0) facts.push(`Cartera: ${money(m.due)} por cobrar${m.overdue.length ? `, de los cuales ${money(m.overdueAmt)} están vencidos (${m.overdue.length} venta(s); la más antigua lleva ${Math.max(...m.overdue.map(x => x.days))} días)` : ''}.`);
  if (m.comp && m.comp.share != null && m.comp.share < 0.999) facts.push(`Este lote lleva ${pct(m.comp.share)} del costo de su orden (${money(m.lotCost)} de ${money(m.comp.total)}); el resto pertenece a otros lotes de la misma orden.`);
  if (m.o && num(m.o.yield_pct) > 0) facts.push(`Rendimiento de la orden: ${pct(num(m.o.yield_pct))}; merma de ${qty(num(m.o.waste_quantity_base))} sobre ${qty(num(m.o.output_quantity_base) + num(m.o.waste_quantity_base))} de entrada.`);
  const reading = panel('Lectura del lote', 'Lo que dicen los datos', `<ul class="list">${facts.map(f => `<li><span class="pill soft">•</span><p>${esc(f)}</p></li>`).join('')}</ul>`, 's12');

  let cost = '';
  if (m.comp) {
    const sh = m.comp.share == null ? 1 : m.comp.share;
    const rows = m.comp.rows;
    cost = panel('Estructura del costo', 'De qué está hecho el costo del lote', `
      <span class="lbl">Costo del lote</span><div class="big">${money(m.lotCost)}</div>
      <p class="muted">${money(m.unitCost, 2)} por ${U} · ${qty(m.initial)} ${U}</p>
      <div class="bar" role="img" aria-label="Composición del costo: ${esc(rows.map(r => r.k + ' ' + pct(r.v / m.comp.sumRows)).join(', '))}">${rows.map(r => `<i class="fill" title="${esc(r.k)}" style="width:${r.v / m.comp.sumRows * 100}%;background:${r.c}"></i>`).join('')}</div>
      <div class="legend">${rows.map(r => `<div class="row"><span class="dot" style="background:${r.c}"></span><span>${esc(r.k)}<br><span class="muted">${pct(r.v / m.comp.sumRows)} del costo</span></span><span class="num">${money(r.v * sh)}</span><span class="num muted">${money(r.v * sh / m.initial, 2)}/${U}</span></div>`).join('')}</div>
      <p class="muted" style="margin-top:12px">${sh < 0.999 ? `Se reparte el costo de la orden (${money(m.comp.total)}) en la proporción del lote (${pct(sh)}).` : 'El lote lleva el costo completo de su orden.'}</p>`, 's5', true);
  } else cost = panel('Estructura del costo', 'Sin orden de producción', `<p class="muted">Este lote no tiene orden asociada. Su costo es el de compra: ${money(m.unitCost, 2)} por ${U}.</p>`, 's5');

  const mx = Math.max(m.rev, m.cogs, 1);
  const econ = panel('Del ingreso al margen', 'Economía de lo vendido', `
    <div class="hb">
      <div class="it"><div class="top"><span>Ingreso neto</span><strong>${money(m.rev)}</strong></div>${track(m.rev, mx, 'var(--forest)')}</div>
      <div class="it"><div class="top"><span>Costo de ventas</span><strong>${money(m.cogs)}</strong></div>${track(m.cogs, mx, 'var(--copper)')}</div>
      <div class="it"><div class="top"><span>Margen bruto</span><strong>${money(m.margin)} · ${pct(m.marginPct)}</strong></div>${track(Math.max(0, m.margin), mx, 'var(--sage)')}</div>
    </div>
    <div class="stat3"><div><span class="lbl">Precio promedio</span><strong>${money(m.avgPrice, 2)}</strong></div><div><span class="lbl">Costo unitario</span><strong>${money(m.avgCost, 2)}</strong></div><div><span class="lbl">Margen unitario</span><strong>${m.avgPrice != null ? money(m.avgPrice - m.avgCost, 2) : '—'}</strong></div></div>
    <div class="note">Margen bruto: no incluye flete de venta, comisiones, muestras, gastos fijos ni impuestos de renta. El IVA (${money(m.tax)}) está fuera del ingreso.</div>`, 's7');

  const recMax = Math.max(m.initial, m.breakeven || 0, 1);
  const rec = panel('Recuperación del lote', 'Punto de equilibrio y saldo', `
    <div class="hb">
      <div class="it"><div class="top"><span>Vendido</span><strong>${qty(m.q)} ${U}</strong></div>${track(m.q, recMax, 'var(--forest)')}</div>
      <div class="it"><div class="top"><span>Punto de equilibrio al precio promedio</span><strong>${m.breakeven != null ? qty(m.breakeven) + ' ' + U : '—'}</strong></div>${track(m.breakeven || 0, recMax, 'var(--gold)')}</div>
      <div class="it"><div class="top"><span>Producido</span><strong>${qty(m.initial)} ${U}</strong></div>${track(m.initial, recMax, '#b9c2b8')}</div>
    </div>
    <div class="stat3"><div><span class="lbl">Saldo ${m.invAvail ? '' : 'teórico'}</span><strong>${qty(m.remaining)} ${U}</strong></div><div><span class="lbl">Valor del saldo a costo</span><strong>${money(m.invValue)}</strong></div><div><span class="lbl">Cobrado del costo</span><strong>${m.lotCost > 0 ? pct(m.paid / m.lotCost) : '—'}</strong></div></div>
    ${m.invAvail ? '' : '<div class="note">El saldo es producido − vendido. Ejecuta la consulta de inventario para contrastarlo con el saldo real.</div>'}`, 's5');

  const sorted = [...m.ventas].sort((a, b) => dval(a.sale_date) - dval(b.sale_date));
  let line = '<p class="muted">Sin ventas.</p>';
  if (sorted.length) {
    const t0 = dval(sorted[0].sale_date), t1 = Math.max(dval(sorted[sorted.length - 1].sale_date), dval(m.cutoff)), W = 560, H = 190, pl = 44, pr = 16, pt = 14, pb = 34;
    let c = 0; const pts = sorted.map(v => { c += num(v.cantidad_base); return [pl + (t1 === t0 ? 0 : (dval(v.sale_date) - t0) / (t1 - t0)) * (W - pl - pr), c, v]; });
    const yMax = Math.max(c, 1), yy = v => H - pb - v / yMax * (H - pb - pt);
    let d = `M${pl},${yy(0)}`; let prev = 0; pts.forEach(p => { d += ` L${p[0].toFixed(1)},${yy(prev).toFixed(1)} L${p[0].toFixed(1)},${yy(p[1]).toFixed(1)}`; prev = p[1]; });
    d += ` L${W - pr},${yy(prev)}`;
    line = `<div class="tw"><svg viewBox="0 0 ${W} ${H}" width="100%" role="img" aria-label="Unidades acumuladas vendidas entre ${dstr(sorted[0].sale_date)} y ${dstr(m.cutoff)}: ${qty(c)}">
      <line x1="${pl}" y1="${yy(0)}" x2="${W - pr}" y2="${yy(0)}" stroke="#d4d6cc"/><line x1="${pl}" y1="${yy(yMax)}" x2="${W - pr}" y2="${yy(yMax)}" stroke="#e8e8df" stroke-dasharray="3 4"/>
      <path d="${d}" fill="none" stroke="#14382d" stroke-width="2.2"/>
      ${pts.map(p => `<circle cx="${p[0].toFixed(1)}" cy="${yy(p[1]).toFixed(1)}" r="4.2" fill="#b47755"><title>${dstr(p[2].sale_date)} · acumulado ${qty(p[1])}</title></circle>`).join('')}
      <text x="${pl - 8}" y="${yy(0) + 4}" text-anchor="end" font-size="10" fill="#6d796f">0</text><text x="${pl - 8}" y="${yy(yMax) + 4}" text-anchor="end" font-size="10" fill="#6d796f">${qty(yMax)}</text>
      <text x="${pl}" y="${H - 10}" font-size="10" fill="#6d796f">${dstr(sorted[0].sale_date)}</text><text x="${W - pr}" y="${H - 10}" text-anchor="end" font-size="10" fill="#6d796f">${dstr(m.cutoff)} (corte)</text></svg></div>`;
  }
  const pace = panel('Ritmo de venta', 'Unidades acumuladas en el tiempo', line, 's7');

  const bMax = Math.max(...m.buckets.map(b => b[1]), 1), bColors = ['var(--sage)', 'var(--gold)', 'var(--copper)', 'var(--terra)'];
  const aging = panel('Cartera', 'Cuánto falta por cobrar y desde cuándo', `<div class="hb">${m.buckets.map((b, i) => `<div class="it"><div class="top"><span>${b[0]}</span><strong>${money(b[1])}</strong></div>${track(b[1], bMax, bColors[i])}</div>`).join('')}</div>
    <div class="note">Días calculados contra el corte (${dstr(m.cutoff)}) y la fecha de vencimiento de cada venta. El cobro del lote se atribuye en proporción al total de cada venta.</div>`, 's5');

  let proc = '<p class="muted">Sin ejecuciones de proceso registradas.</p>';
  if (m.ejec.length) {
    const first = m.ejec[0], inp = num(first.input_quantity_base), outp = num(m.o ? m.o.output_quantity_base : first.output_quantity_base), was = num(m.o ? m.o.waste_quantity_base : first.waste_quantity_base), tot = inp || outp + was;
    proc = `<div class="tw"><table><thead><tr><th>#</th><th>Proceso</th><th>Ejecutor</th><th>Estado</th><th class="r">Entrada</th><th class="r">Salida</th><th class="r">Merma</th><th class="r">Rend.</th><th class="r">Pactado</th><th class="r">Real</th><th class="r">Desv.</th></tr></thead><tbody>
      ${m.ejec.map(e => `<tr><td>${esc(e.sequence_no)}</td><td><strong>${esc(e.proceso)}</strong></td><td>${esc(e.ejecutor || 'Propio')}<br><span class="muted">${e.executor_type === 'EXTERNAL' ? 'Maquila externa' : 'Interno'}</span></td><td><span class="pill ${e.status === 'DONE' || e.status === 'RECEIVED' ? 'ok' : 'warn'}">${esc(e.status)}</span></td><td class="r">${qty(num(e.input_quantity_base))}</td><td class="r">${qty(num(e.output_quantity_base))}</td><td class="r">${qty(num(e.waste_quantity_base))}</td><td class="r">${pct(num(e.yield_pct))}</td><td class="r">${money(num(e.computed_cost))}</td><td class="r">${e.actual_cost == null ? '—' : money(num(e.actual_cost))}</td><td class="r">${e.desviacion == null ? '—' : money(num(e.desviacion))}</td></tr>`).join('')}</tbody></table></div>
      <div class="bar" style="background:#e9e4d6;margin-top:18px" role="img" aria-label="Entrada ${qty(tot)}: salida ${qty(outp)}, merma ${qty(was)}"><i class="fill" style="width:${tot > 0 ? outp / tot * 100 : 0}%;background:var(--forest)"></i><i class="fill" style="width:${tot > 0 ? was / tot * 100 : 0}%;background:var(--copper)"></i></div>
      <p class="muted">Salida ${qty(outp)} · merma ${qty(was)} · entrada ${qty(tot)} (unidad base de la orden). Rendimiento ${pct(tot > 0 ? outp / tot : null)}.</p>`;
  }
  const process = panel('Proceso y rendimiento', 'Producción de la orden completa', proc, 's12');

  const gap = !(L.farm_name || m.padres.some(p => p.farm_name));
  const chain = `<div class="chain">
    <div class="node ${gap ? 'gap' : ''}"><small>Origen</small><b>${esc(L.farm_name || (m.padres.find(p => p.farm_name) || {}).farm_name || 'Finca sin registrar')}</b><small>${gap ? 'Falta finca, municipio y cosecha' : esc([L.municipality_name, L.harvest_year].filter(Boolean).join(' · '))}</small></div><span class="arrow">→</span>
    ${m.padres.length ? m.padres.map(p => `<div class="node"><small>Lote padre · ${pct(num(p.contribution_pct), 1)}</small><b>${esc(p.lote_padre)}</b><small>${esc(p.producto)}<br>${qty(num(p.quantity_consumed), 2)} ${esc(p.unidad_consumo)}${p.costo_consumido != null ? ' · ' + money(num(p.costo_consumido)) : ''}</small></div>`).join('') : '<div class="node"><small>Lote padre</small><b>—</b><small>Sin linaje registrado</small></div>'}<span class="arrow">→</span>
    <div class="node"><small>Orden</small><b>${esc(L.order_number || '—')}</b><small>${m.ejec.map(e => esc(e.proceso)).join(', ') || 'Sin ejecuciones'}</small></div><span class="arrow">→</span>
    <div class="node"><small>Lote</small><b>${esc(L.batch_code)}</b><small>${qty(m.initial)} ${U}</small></div><span class="arrow">→</span>
    <div class="node"><small>Ventas</small><b>${m.ventas.length} venta(s)</b><small>${new Set(m.ventas.map(v => v.cliente)).size} cliente(s)</small></div></div>
    ${m.hijos.length ? `<p class="muted" style="margin-top:12px">Este lote alimentó a: ${m.hijos.map(h => esc(h.lote_hijo)).join(', ')}.</p>` : ''}`;
  const trace = panel('Trazabilidad', 'De la finca a la taza', chain, 's12');

  const ctl = panel('Confianza del dato', `${ctr.length} controles`, `<ul class="list">${ctr.map(x => `<li><span class="pill ${PILL[x.state][0]}">${PILL[x.state][1]}</span><p><strong>${esc(x.name)}</strong><span class="muted">${esc(x.detail)}</span></p></li>`).join('')}</ul>`, 's12');

  const sales = panel('Detalle', 'Ventas atribuidas al lote', m.ventas.length ? `<div class="tw scroll" tabindex="0" role="region" aria-label="Ventas del lote; desplazable"><table><thead><tr><th>Fecha</th><th>Venta</th><th>Cliente</th><th>Canal</th><th class="r">Cant.</th><th class="r">Ingreso</th><th class="r">Costo</th><th class="r">Margen</th><th class="r">Cobrado</th><th class="r">Por cobrar</th><th>Vence</th></tr></thead><tbody>
    ${sorted.map(v => { const dd = v.due_date && num(v.por_cobrar_atribuido) > 0.005 ? dayDiff(m.cutoff, v.due_date) : null; return `<tr><td class="nw">${dstr(v.sale_date)}</td><td class="nw"><strong>${esc(v.sale_number)}</strong><br><span class="pill ${v.payment_status === 'PAID' ? 'ok' : v.payment_status === 'PARTIAL' ? 'info' : 'warn'}">${esc(v.payment_status)}</span></td><td>${who(v.cliente)}</td><td>${esc(v.channel)}</td><td class="r">${qty(num(v.cantidad_base))}</td><td class="r">${money(num(v.ingreso_neto))}</td><td class="r">${money(num(v.costo_ventas), 2)}</td><td class="r">${money(num(v.margen), 2)}<br><span class="muted">${pct(num(v.margen_pct))}</span></td><td class="r">${money(num(v.cobrado_atribuido))}</td><td class="r">${money(num(v.por_cobrar_atribuido))}</td><td class="nw">${dstr(v.due_date)}${dd == null ? '' : dd > 0 ? `<br><span class="pill bad">${dd} d vencida</span>` : dd === 0 ? '<br><span class="pill warn">vence hoy</span>' : ''}</td></tr>`; }).join('')}
    <tr><td colspan="4"><strong>Total</strong></td><td class="r"><strong>${qty(m.q)}</strong></td><td class="r"><strong>${money(m.rev)}</strong></td><td class="r"><strong>${money(m.cogs, 2)}</strong></td><td class="r"><strong>${money(m.margin, 2)}</strong></td><td class="r"><strong>${money(m.paid)}</strong></td><td class="r"><strong>${money(m.due)}</strong></td><td></td></tr></tbody></table></div>` : '<p class="muted">Sin ventas confirmadas, despachadas o entregadas para este lote.</p>', 's12');

  app.innerHTML = head + kpis + `<div class="grid">${reading}${cost}${econ}${rec}${pace}${aging}${process}${trace}${ctl}${sales}</div>
    <p class="foot">Documento de solo lectura generado desde el ERP. Contiene datos personales de clientes: no lo compartas públicamente (usa “Ocultar nombres de clientes” antes de imprimir). Margen bruto = ingreso neto − costo de ventas congelado al vender. No incluye flete de venta, comisiones ni gastos del periodo.</p>`;
  document.title = 'Informe del lote ' + L.batch_code + ' · Densa Niebla';
  animate();
}

function fmtBy(f, v) { return f === 'money' ? money(v) : f === 'pct' ? pct(v) : qty(v); }

function animate() {
  const first = state.first; state.first = false;
  const reduce = matchMedia('(prefers-reduced-motion: reduce)').matches;
  if (!first || reduce || !window.gsap) return;
  gsap.from('.reveal', {y: 16, opacity: 0, duration: .5, stagger: .05, ease: 'power3.out', clearProps: 'transform,opacity'});
  gsap.from('.fill', {scaleX: 0, transformOrigin: 'left center', duration: .8, delay: .25, stagger: .02, ease: 'power2.out', clearProps: 'transform'});
  document.querySelectorAll('[data-count]').forEach(el => {
    const t = parseFloat(el.dataset.count); if (isNaN(t)) return; const o = {v: 0};
    gsap.to(o, {v: t, duration: 1.1, ease: 'power2.out', onUpdate: () => { el.textContent = fmtBy(el.dataset.fmt, o.v); }, onComplete: () => { el.textContent = fmtBy(el.dataset.fmt, t); }});
  });
}

document.getElementById('btn-mask').addEventListener('click', e => { state.mask = !state.mask; e.currentTarget.setAttribute('aria-pressed', state.mask); e.currentTarget.textContent = state.mask ? 'Mostrar nombres de clientes' : 'Ocultar nombres de clientes'; render(); });
document.getElementById('btn-print').addEventListener('click', () => window.print());
window.__informe = {derive, controls};
window.addEventListener('load', render);
if (document.readyState === 'complete') render();
})();
</script>
</body>
</html>
"""


SECTIONS = ["identidad", "padres", "hijos", "orden", "ejecuciones", "costos_adicionales",
            "insumos", "libro", "ventas", "inventario", "controles"]


def _load_env_file():
    for name in (".env", ".flaskenv"):
        p = Path(name)
        if p.is_file():
            for line in p.read_text(encoding="utf-8", errors="ignore").splitlines():
                m = re.match(r"\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)\s*$", line)
                if m and not line.lstrip().startswith("#"):
                    os.environ.setdefault(m.group(1), m.group(2).strip().strip("'\""))


def resolve_dsn(arg):
    if arg:
        return arg
    _load_env_file()
    for key in ("DATABASE_URL", "SQLALCHEMY_DATABASE_URI", "DEV_DATABASE_URL"):
        if os.environ.get(key):
            return os.environ[key]
    sys.exit("No encuentro la conexion. Usa --dsn o define DATABASE_URL.")


def connect(dsn):
    """Devuelve (conexion, estilo_de_parametro). Siempre en modo solo lectura."""
    if dsn.startswith("sqlite:///"):
        import sqlite3
        return sqlite3.connect(dsn[len("sqlite:///"):]), "sqlite"
    dsn = re.sub(r"^postgres(ql)?(\+\w+)?://", "postgresql://", dsn)
    try:
        import psycopg2
        con = psycopg2.connect(dsn)
        con.set_session(readonly=True, autocommit=False)
    except ImportError:
        try:
            import psycopg
        except ImportError:
            sys.exit("Falta el driver: pip install psycopg2-binary")
        con = psycopg.connect(dsn)
        con.read_only = True
    cur = con.cursor()
    try:
        cur.execute("SET LOCAL statement_timeout = '30s'")
    except Exception:
        con.rollback()
    return con, "pg"


def run(con, style, sql, params=None):
    marker = ":p" if style == "sqlite" else "%(p)s"
    text = sql.replace("{{BATCH}}", marker)
    cur = con.cursor()
    cur.execute(text, {"p": params} if "{{BATCH}}" in sql else None) if "{{BATCH}}" in sql else cur.execute(text)
    cols = [c[0] for c in cur.description]
    return [dict(zip(cols, row)) for row in cur.fetchall()]


class _Enc(json.JSONEncoder):
    def default(self, o):
        if isinstance(o, decimal.Decimal):
            return float(o)
        if isinstance(o, (dt.datetime, dt.date)):
            return o.isoformat()
        return str(o)


def collect(con, style, code, cutoff, source="ERP"):
    data = {"meta": {"batch_code": code, "cutoff": cutoff, "source": source,
                     "generated_at": dt.datetime.now().isoformat(timespec="seconds")}}
    for key in SECTIONS:
        data[key] = run(con, style, QUERIES[key], code)
    return json.loads(json.dumps(data, cls=_Enc))


def render(data, out_dir):
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    code = data["meta"]["batch_code"]
    safe = re.sub(r"[^A-Za-z0-9_.-]+", "_", code)
    payload = json.dumps(data, ensure_ascii=False, cls=_Enc).replace("</", "<\\/")
    html = TEMPLATE.replace("/*__DATA__*/null", payload)
    html_path, json_path = out / f"informe_{safe}.html", out / f"informe_{safe}.json"
    html_path.write_text(html, encoding="utf-8")
    json_path.write_text(json.dumps(data, ensure_ascii=False, indent=1, cls=_Enc), encoding="utf-8")
    return html_path, json_path


def main(argv=None):
    ap = argparse.ArgumentParser(description="Informe de lote (solo lectura)")
    ap.add_argument("batch_code", nargs="?", help="codigo del lote (batches.batch_code)")
    ap.add_argument("--dsn", help="cadena de conexion; por defecto DATABASE_URL")
    ap.add_argument("--list", action="store_true", help="lista los ultimos lotes")
    ap.add_argument("--from-json", help="reconstruye el tablero desde un JSON guardado")
    ap.add_argument("--cutoff", help="fecha de corte AAAA-MM-DD (por defecto hoy)")
    ap.add_argument("--out", default="informes", help="carpeta de salida")
    ap.add_argument("--open", action="store_true", help="abre el HTML al terminar")
    a = ap.parse_args(argv)

    if a.from_json:
        data = json.loads(Path(a.from_json).read_text(encoding="utf-8"))
        if a.cutoff:
            data["meta"]["cutoff"] = a.cutoff
    else:
        dsn = resolve_dsn(a.dsn)
        con, style = connect(dsn)
        try:
            if a.list:
                for r in run(con, style, LIST_SQL):
                    print(f"{r['batch_code']:<28} {r['batch_type']:<10} {r['status']:<9} {str(r['production_date'] or ''):<11} {r['producto']}")
                return 0
            if not a.batch_code:
                ap.error("indica el codigo del lote o usa --list")
            cutoff = a.cutoff or dt.date.today().isoformat()
            data = collect(con, style, a.batch_code, cutoff)
            if not data["identidad"]:
                near = run(con, style, LIST_SQL)
                print(f"No existe el lote '{a.batch_code}'. Ultimos lotes:")
                for r in near[:10]:
                    print("  ", r["batch_code"], "-", r["producto"])
                return 2
        finally:
            try:
                con.rollback()
                con.close()
            except Exception:
                pass
    html_path, json_path = render(data, a.out)
    print(f"Informe: {html_path}\nCopia de datos: {json_path}")
    if a.open:
        import webbrowser
        webbrowser.open(html_path.resolve().as_uri())
    return 0


if __name__ == "__main__":
    sys.exit(main())
