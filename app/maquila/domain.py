from datetime import date, timedelta
from decimal import Decimal, InvalidOperation

def decimal_value(value):
    try:
        d = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        raise ValueError("Cantidad o costo inválido.")
    if not d.is_finite() or d <= 0:
        raise ValueError("El valor debe ser finito y mayor que cero.")
    return d

def business_due(start, days):
    # Solo lunes a viernes. No descuenta festivos.
    result = start
    for _ in range(days):
        result += timedelta(days=1)
        while result.weekday() >= 5:
            result += timedelta(days=1)
    return result

def forecast(kg, history, grams, quote=None):
    valid = [r for r in history if Decimal(str(r['input'])) > 0 and
             0 < Decimal(str(r['output'])) <= Decimal(str(r['input']))]
    total_in = sum((Decimal(str(r['input'])) for r in valid), Decimal(0))
    total_out = sum((Decimal(str(r['output'])) for r in valid), Decimal(0))
    ratio = total_out / total_in if total_in else None
    weight = kg * ratio if ratio is not None else None
    return {'n':len(valid), 'yield':str(ratio) if ratio is not None else None,
            'kg':str(weight) if weight is not None else None,
            'units':int(weight * 1000 / grams) if weight is not None else None,
            'grams':str(grams), 'maquila_quote':str(quote) if quote is not None else None,
            'basis':'Solo pesos de ejecuciones del mismo proceso y maquilador; no estima empaques ni margen.'}
