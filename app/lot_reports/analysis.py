"""Analisis de un lote: funciones puras (sin Flask ni base de datos).

Recibe los datos crudos de las consultas (ver queries.py) y devuelve todo lo que
necesita la pantalla: indicadores, composicion del costo, cartera, linea de tiempo,
controles de confianza y lectura del lote.
"""
from __future__ import annotations

import math
from datetime import date, datetime
from decimal import ROUND_HALF_UP, Decimal

ZERO = Decimal(0)
LETTERS = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"


def num(value) -> Decimal:
    if value is None or value == "":
        return ZERO
    if isinstance(value, Decimal):
        return value
    try:
        return Decimal(str(value))
    except Exception:
        return ZERO


def as_date(value):
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def _grouped(value: Decimal, decimals: int) -> str:
    value = value.quantize(Decimal(1).scaleb(-decimals), rounding=ROUND_HALF_UP)
    text = f"{abs(value):,.{decimals}f}"
    text = text.replace(",", "\x00").replace(".", ",").replace("\x00", ".")
    return ("-" if value < 0 else "") + text


def money(value, decimals: int = 0) -> str:
    if value is None:
        return "—"
    s = _grouped(num(value), decimals)
    return ("-$ " + s[1:]) if s.startswith("-") else "$ " + s


def qty(value, decimals: int = 2) -> str:
    if value is None:
        return "—"
    v = num(value)
    return _grouped(v, 0 if v == v.to_integral_value() else decimals)


def pct(value, decimals: int = 1) -> str:
    if value is None:
        return "—"
    return _grouped(num(value) * 100, decimals) + " %"


def fdate(value) -> str:
    d = as_date(value)
    return d.strftime("%d/%m/%Y") if d else "—"


def width(value, maximum) -> float:
    maximum = num(maximum)
    if maximum <= 0:
        return 0.0
    return float(max(ZERO, min(Decimal(100), num(value) / maximum * 100)))


def _sum(rows, key) -> Decimal:
    return sum((num(r.get(key)) for r in rows or []), ZERO)


def build_report(data: dict, cutoff=None) -> dict | None:
    ident = data.get("identidad") or []
    if not ident:
        return None
    meta = data.get("meta") or {}
    cutoff = as_date(cutoff) or as_date(meta.get("cutoff")) or date.today()
    lot = ident[0]
    ventas = sorted(data.get("ventas") or [], key=lambda v: (str(v.get("sale_date")), str(v.get("sale_number"))))
    padres, hijos = data.get("padres") or [], data.get("hijos") or []
    ejec, ins = data.get("ejecuciones") or [], data.get("insumos") or []
    inv_rows = data.get("inventario") or []
    order = (data.get("orden") or [None])[0]

    unit = lot.get("unidad") or ""
    initial, unit_cost = num(lot.get("initial_quantity")), num(lot.get("unit_cost"))
    lot_cost = num(lot.get("valor_inicial")) or initial * unit_cost
    q, rev, tax, cogs = (_sum(ventas, k) for k in ("cantidad_base", "ingreso_neto", "impuesto", "costo_ventas"))
    paid, due = _sum(ventas, "cobrado_atribuido"), _sum(ventas, "por_cobrar_atribuido")
    avg_price = rev / q if q > 0 else None
    avg_cost = cogs / q if q > 0 else None
    margin = rev - cogs
    margin_pct = margin / rev if rev > 0 else None
    sell_through = q / initial if initial > 0 else None
    breakeven = math.ceil(lot_cost / avg_price) if avg_price and avg_price > 0 else None
    pot_rev = initial * avg_price if avg_price is not None else None
    has_inv = bool(inv_rows)
    remaining_theo = initial - q
    remaining_real = _sum(inv_rows, "quantity_base") if has_inv else None
    remaining = remaining_real if remaining_real is not None else remaining_theo
    inv_value = _sum(inv_rows, "total_value") if has_inv else remaining * unit_cost

    m = {
        "lot": lot, "order": order, "cutoff": cutoff, "unit": unit, "initial": initial, "unit_cost": unit_cost,
        "lot_cost": lot_cost, "qty_sold": q, "revenue": rev, "tax": tax, "cogs": cogs, "paid": paid, "due": due,
        "avg_price": avg_price, "avg_cost": avg_cost, "margin": margin, "margin_pct": margin_pct,
        "sell_through": sell_through, "breakeven": breakeven, "pot_rev": pot_rev,
        "pot_margin": (pot_rev - lot_cost) if pot_rev is not None else None,
        "recovered": (rev / lot_cost) if lot_cost > 0 else None,
        "paid_of_cost": (paid / lot_cost) if lot_cost > 0 else None,
        "has_inventory": has_inv, "remaining": remaining, "remaining_theo": remaining_theo,
        "remaining_real": remaining_real, "inventory_value": inv_value,
        "padres": padres, "hijos": hijos, "ejecuciones": ejec, "insumos": ins,
    }

    comp = None
    if order:
        raw = _sum([i for i in ins if i.get("product_kind") == "RAW_MATERIAL"], "costo_total")
        sup = _sum([i for i in ins if i.get("product_kind") == "SUPPLY"], "costo_total")
        other = max(ZERO, num(order.get("total_input_cost")) - raw - sup)
        total_cost = num(order.get("total_cost"))
        share = min(Decimal(1), lot_cost / total_cost) if total_cost > 0 else None
        rows = [
            ("Materia prima (café)", raw, "#d8bd77"), ("Empaque e insumos", sup, "#5da677"),
            ("Otros insumos", other, "#b9c2b8"), ("Proceso / maquila", num(order.get("total_process_cost")), "#b47755"),
            ("Estructura / transporte", num(order.get("total_overhead_cost")), "#ffffff"),
        ]
        rows = [r for r in rows if r[1] > Decimal("0.005")]
        sum_rows = sum((r[1] for r in rows), ZERO)
        sh = share if share is not None else Decimal(1)
        comp = {
            "total": total_cost, "share": share, "sum": sum_rows,
            "rows": [{"label": r[0], "value": r[1], "color": r[2], "pct_total": (r[1] / sum_rows if sum_rows else ZERO),
                      "width": float(r[1] / sum_rows * 100) if sum_rows else 0.0,
                      "lot_value": r[1] * sh, "per_unit": (r[1] * sh / initial) if initial > 0 else None} for r in rows],
        }
    m["composition"] = comp

    overdue = []
    buckets = [["Vence hoy o después", ZERO], ["1 a 30 días", ZERO], ["31 a 60 días", ZERO], ["Más de 60 días", ZERO]]
    sales_rows, names = [], {}
    for v in ventas:
        pend = num(v.get("por_cobrar_atribuido"))
        dd = as_date(v.get("due_date"))
        days = (cutoff - dd).days if dd else None
        if pend > Decimal("0.005") and days is not None and days > 0:
            overdue.append((v, days))
        if pend > Decimal("0.005"):
            idx = 0 if (days is None or days <= 0) else 1 if days <= 30 else 2 if days <= 60 else 3
            buckets[idx][1] += pend
        client = v.get("cliente") or "—"
        if client not in names:
            names[client] = "Cliente " + LETTERS[len(names) % 26]
        sales_rows.append({**v, "days_overdue": days if (pend > Decimal("0.005") and days is not None) else None, "mask": names[client]})
    m["overdue_count"] = len(overdue)
    m["overdue_amount"] = sum((num(v.get("por_cobrar_atribuido")) for v, _ in overdue), ZERO)
    m["oldest_overdue_days"] = max([d for _, d in overdue], default=None)
    m["overdue_statuses"] = sorted({v.get("payment_status") for v, _ in overdue})
    bmax = max([b[1] for b in buckets] + [Decimal(1)])
    colors = ["#5da677", "#d8bd77", "#b47755", "#a0443c"]
    m["buckets"] = [{"label": b[0], "amount": b[1], "width": width(b[1], bmax), "color": colors[i]} for i, b in enumerate(buckets)]
    m["sales"] = sales_rows

    def group(key):
        g = {}
        for v in ventas:
            k = v.get(key) or "—"
            x = g.setdefault(k, {"label": k, "rev": ZERO, "cogs": ZERO, "q": ZERO, "n": 0})
            x["rev"] += num(v.get("ingreso_neto")); x["cogs"] += num(v.get("costo_ventas"))
            x["q"] += num(v.get("cantidad_base")); x["n"] += 1
        return sorted(g.values(), key=lambda x: -x["rev"])
    ch, cl = group("channel"), group("cliente")
    mx = max([x["rev"] for x in ch + cl] + [Decimal(1)])
    for x in ch + cl:
        x["margin_pct"] = (x["rev"] - x["cogs"]) / x["rev"] if x["rev"] > 0 else None
        x["width"] = width(x["rev"], mx)
        x["mask"] = names.get(x["label"], x["label"])
    m["by_channel"], m["by_client"] = ch, cl

    rec_max = max(initial, Decimal(breakeven or 0), Decimal(1))
    m["rec_bars"] = {"sold": width(q, rec_max), "breakeven": width(breakeven or 0, rec_max), "initial": width(initial, rec_max)}
    emax = max(rev, cogs, Decimal(1))
    m["econ_bars"] = {"rev": width(rev, emax), "cogs": width(cogs, emax), "margin": width(max(ZERO, margin), emax)}

    timeline = None
    if ventas:
        W, H, pl, pr, pt, pb = 560, 190, 44, 16, 14, 34
        t0 = as_date(ventas[0].get("sale_date"))
        t1 = max(as_date(ventas[-1].get("sale_date")), cutoff)
        span = (t1 - t0).days
        y_max = max(sum((num(v.get("cantidad_base")) for v in ventas), ZERO), Decimal(1))

        def yy(val):
            return float(H - pb - val / y_max * (H - pb - pt))
        cum, pts = ZERO, []
        for v in ventas:
            cum += num(v.get("cantidad_base"))
            x = pl + ((as_date(v.get("sale_date")) - t0).days / span if span else 0) * (W - pl - pr)
            pts.append({"x": round(x, 1), "y": round(yy(cum), 1), "cum": cum, "date": as_date(v.get("sale_date"))})
        path, prev = f"M{pl},{round(yy(ZERO), 1)}", ZERO
        for p in pts:
            path += f" L{p['x']},{round(yy(prev), 1)} L{p['x']},{p['y']}"
            prev = p["cum"]
        path += f" L{W - pr},{round(yy(prev), 1)}"
        timeline = {"W": W, "H": H, "pl": pl, "pr": pr, "path": path, "points": pts, "y0": round(yy(ZERO), 1),
                    "y1": round(yy(y_max), 1), "ymax": y_max, "start": t0, "end": cutoff, "total": cum}
    m["timeline"] = timeline

    proc = None
    if ejec:
        first = ejec[0]
        inp = num(first.get("input_quantity_base"))
        out = num(order.get("output_quantity_base")) if order else num(first.get("output_quantity_base"))
        waste = num(order.get("waste_quantity_base")) if order else num(first.get("waste_quantity_base"))
        tot = inp or (out + waste)
        proc = {"input": tot, "output": out, "waste": waste, "yield": (out / tot) if tot > 0 else None,
                "w_out": float(out / tot * 100) if tot > 0 else 0.0, "w_waste": float(waste / tot * 100) if tot > 0 else 0.0}
    m["process"] = proc

    farm = lot.get("farm_name") or next((p.get("farm_name") for p in padres if p.get("farm_name")), None)
    m["origin_gap"] = not farm
    m["origin_name"] = farm or "Finca sin registrar"
    m["origin_detail"] = " · ".join(str(x) for x in (lot.get("municipality_name"), lot.get("harvest_year")) if x)
    m["customers"] = len({v.get("cliente") for v in ventas})

    m["controls"] = controls(data, m)
    m["facts"] = facts(m)
    m["controls_bad"] = sum(1 for c in m["controls"] if c["state"] == "REVISAR")
    m["controls_info"] = sum(1 for c in m["controls"] if c["state"] == "INFO")
    return m


def controls(data: dict, m: dict) -> list[dict]:
    c: list[dict] = []

    def add(name, state, detail):
        c.append({"name": name, "state": state, "detail": detail})
    lot, order, padres, ejec, ins = m["lot"], m["order"], m["padres"], m["ejecuciones"], m["insumos"]
    adic = data.get("costos_adicionales") or []
    ventas = data.get("ventas") or []
    farm = lot.get("farm_name") or any(p.get("farm_name") for p in padres)
    add("Origen: finca registrada", "OK" if farm else "REVISAR",
        "El lote o sus padres tienen finca" if farm else "Ni el lote ni sus padres tienen finca, municipio o cosecha: se pierde la historia de origen")
    if padres:
        s = _sum(padres, "contribution_pct")
        add("Linaje: aportes de padres suman 100 %", "OK" if abs(s - 1) <= Decimal("0.0015") else "INFO",
            f"Suma {pct(s, 2)}" + (": el resto de la orden alimenta otros lotes" if s < Decimal("0.9985") else ""))
    if order:
        tc = num(order.get("total_cost"))
        parts = num(order.get("total_input_cost")) + num(order.get("total_process_cost")) + num(order.get("total_overhead_cost"))
        add("Orden: café + proceso + estructura = costo total", "OK" if abs(parts - tc) < 1 else "REVISAR", f"Suma {money(parts)} frente a {money(tc)}")
        if ins:
            d_ = _sum(ins, "costo_total")
            add("Orden: insumos detallados = costo de insumos", "OK" if abs(d_ - num(order.get("total_input_cost"))) < 1 else "REVISAR",
                f"Detalle {money(d_)} frente a {money(num(order.get('total_input_cost')))}")
        if ejec:
            e = _sum(ejec, "costo_efectivo")
            add("Maquila: costo efectivo = costo de proceso de la orden", "OK" if abs(e - num(order.get("total_process_cost"))) < 1 else "REVISAR",
                f"Ejecuciones {money(e)} frente a {money(num(order.get('total_process_cost')))}")
            ext = sum(1 for x in ejec if x.get("executor_type") == "EXTERNAL" and x.get("actual_cost") is None)
            add("Maquila externa con costo real facturado", "REVISAR" if ext else "OK",
                f"{ext} ejecución(es) con costo solo calculado" if ext else "Todo con costo real")
        comp = m["composition"]
        if comp and comp["share"] is not None:
            add("Costo del lote ≤ costo de la orden", "OK" if m["lot_cost"] <= tc + 1 else "REVISAR",
                f"El lote lleva {pct(comp['share'])} de la orden; el resto corresponde a otros lotes" if comp["share"] < Decimal("0.999") else "El lote lleva toda la orden")
        proc_cost = num(order.get("total_process_cost"))
        dup = next((a for a in adic if proc_cost > 0 and abs(num(a.get("monto")) - proc_cost) < 1), None)
        if dup:
            add("Costos adicionales vs. proceso", "INFO",
                f'El costo adicional "{dup.get("cost_type")}" ({money(num(dup.get("monto")))}) coincide con el proceso/maquila: es el mismo valor, no se suma dos veces')
        st = order.get("status")
        add("Orden con costeo cerrado", "OK" if st == "CLOSED" else "INFO" if st == "COMPLETED" else "REVISAR",
            "Producción terminada pero el costeo no está cerrado: aún admite imputaciones (p. ej. facturas tardías)" if st == "COMPLETED" else f"Estado de la orden: {st}")
        if order.get("started_at") and str(order.get("started_at")) == str(order.get("completed_at")):
            add("Orden registrada con fechas reales", "INFO", "Inicio y fin son idénticos: parece una orden histórica o reconstruida")
    else:
        add("Orden de producción asociada", "NA", "El lote no tiene orden (p. ej. lote comprado)")
    prod = as_date(lot.get("production_date"))
    if prod:
        pre = [v for v in ventas if as_date(v.get("sale_date")) and as_date(v.get("sale_date")) < prod]
        add("Ventas anteriores a la producción del lote", "INFO" if pre else "OK",
            f"{len(pre)} de {len(ventas)} ventas tienen fecha previa al {fdate(prod)} (preventa o fecha retroactiva)" if pre else "Ninguna")
    if ventas:
        add("Ventas sin cobro registrado", "INFO" if m["paid"] <= Decimal("0.005") else "OK",
            "Cobrado atribuido = 0: confirma que los cobros se registraron en pagos" if m["paid"] <= Decimal("0.005") else f"Cobrado {money(m['paid'])}")
        add("Cartera vencida", "REVISAR" if m["overdue_count"] else "OK",
            f"{m['overdue_count']} venta(s) vencidas por {money(m['overdue_amount'])}; el estado de pago sigue como {'/'.join(m['overdue_statuses'])}" if m["overdue_count"] else "Sin vencidas")
    if m["sell_through"] is not None and lot.get("status") == "ACTIVE":
        add("Ventas trazadas al lote vs. cantidad producida", "INFO" if m["sell_through"] < Decimal("0.1") else "OK",
            f"Solo {pct(m['sell_through'])} de las unidades del lote tiene venta asignada; si se vendió más, falta asignar lote a esas ventas")
    if m["has_inventory"]:
        diff = abs(m["remaining_real"] - m["remaining_theo"])
        add("Inventario real vs. teórico", "OK" if diff < Decimal("0.001") else "REVISAR",
            f"Real {qty(m['remaining_real'])} frente a teórico {qty(m['remaining_theo'])} {m['unit']}")
    else:
        add("Inventario real vs. teórico", "NA", "Sin saldos de inventario cargados para este lote (consulta de inventario sin ejecutar o sin filas): el saldo mostrado es teórico (producido − vendido)")
    for x in data.get("controles") or []:
        est = x.get("estado")
        add(x.get("control"), "OK" if est == "OK" else "NA" if est == "NO APLICA" else "INFO" if est == "INFORMATIVO" else "REVISAR", x.get("detalle"))
    return c


def facts(m: dict) -> list[str]:
    u, f = m["unit"], []
    f.append(f"Se asignaron a ventas {qty(m['qty_sold'])} de {qty(m['initial'])} {u} ({pct(m['sell_through'])}). Lo vendido deja {money(m['revenue'])} de ingreso neto y {money(m['margin'])} de margen bruto ({pct(m['margin_pct'])}).")
    if m["avg_price"] is not None:
        f.append(f"Precio promedio {money(m['avg_price'], 2)} frente a costo unitario {money(m['avg_cost'], 2)} por {u}: margen de {money(m['avg_price'] - m['avg_cost'], 2)} por unidad.")
    if m["breakeven"] is not None:
        f.append(f"El lote ya recuperó su costo ({money(m['lot_cost'])})." if m["qty_sold"] >= m["breakeven"]
                 else f"Para recuperar el costo del lote hacen falta {qty(m['breakeven'])} {u} al precio promedio; faltan {qty(m['breakeven'] - m['qty_sold'])}.")
    if m["pot_rev"] is not None:
        f.append(f"Proyección, no resultado: si se vendiera todo el lote al precio promedio, el ingreso sería {money(m['pot_rev'])} y el margen {money(m['pot_rev'] - m['lot_cost'])}.")
    if m["due"] > 0:
        extra = (f", de los cuales {money(m['overdue_amount'])} están vencidos ({m['overdue_count']} venta(s); la más antigua lleva {m['oldest_overdue_days']} días)" if m["overdue_count"] else "")
        f.append(f"Cartera: {money(m['due'])} por cobrar{extra}.")
    comp, o = m["composition"], m["order"]
    if comp and comp["share"] is not None and comp["share"] < Decimal("0.999"):
        f.append(f"Este lote lleva {pct(comp['share'])} del costo de su orden ({money(m['lot_cost'])} de {money(comp['total'])}); el resto pertenece a otros lotes de la misma orden.")
    if o and num(o.get("yield_pct")) > 0:
        f.append(f"Rendimiento de la orden: {pct(num(o.get('yield_pct')))}; merma de {qty(num(o.get('waste_quantity_base')))} sobre {qty(num(o.get('output_quantity_base')) + num(o.get('waste_quantity_base')))} de entrada.")
    return f


def enrich_lot_row(row: dict) -> dict:
    initial, sold = num(row.get("initial_quantity")), num(row.get("qty_sold"))
    rev, cogs = num(row.get("revenue")), num(row.get("cogs"))
    cost = num(row.get("lot_cost"))
    return {**row,
            "sell_through": (sold / initial) if initial > 0 else None,
            "sell_width": float(min(Decimal(100), sold / initial * 100)) if initial > 0 else 0.0,
            "margin": rev - cogs, "margin_pct": ((rev - cogs) / rev) if rev > 0 else None,
            "recovered": (rev / cost) if cost > 0 else None}
