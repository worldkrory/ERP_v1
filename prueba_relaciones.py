"""Prueba en memoria del grafo de objetos, sin base de datos.

Verifica que las relaciones estan bien configuradas y navegables en ambos
sentidos: es el error que un chequeo de DDL no detecta.
"""
from __future__ import annotations
import datetime as dt, decimal, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from app.models import (Address, Batch, BatchLineage, Party, PartyRole, Product,
                        Role, Sale, SaleItem, SaleItemBatch, UnitOfMeasure, User, UserRole)

D = decimal.Decimal
hoy = dt.date.today()

# Tercero con dos roles: es LA regla de diseno del ERD.
finca = Party(party_type="NATURAL", document_type="CC", document_number="10245678",
              legal_name="Anibal Ramirez", first_name="Anibal", last_name="Ramirez")
finca.party_roles = [PartyRole(role_code="COFFEE_GROWER", valid_from=hoy),
                     PartyRole(role_code="CUSTOMER", valid_from=hoy)]
finca.addresses = [Address(address_type="FARM", address_line="Vereda La Esperanza",
                           municipality_name="Manizales", department_name="Caldas",
                           is_primary=True)]
assert finca.active_roles() == {"COFFEE_GROWER", "CUSTOMER"}, finca.active_roles()
assert finca.has_role("PROCESSOR") is False
assert finca.primary_address is not None
assert finca.display_name == "Anibal Ramirez"

# Usuario vinculado al tercero + rol.
admin = User(email="admin@densaniebla.co", password_hash="x", full_name="Admin")
admin.party = finca
admin.user_roles = [UserRole(role=Role(code="ADMIN", name="Administrador", permissions=[]))]
assert finca.users[0] is admin, "navegacion inversa users<->party rota"
assert admin.role_codes == {"ADMIN"}, admin.role_codes
assert admin.has_role("ADMIN") and admin.is_locked is False

# Linaje de lotes: dos lotes de origen -> un blend.
lb = UnitOfMeasure(code="LB", name="Libra", dimension="MASS")
verde = Product(sku="CV-001", name="Cafe verde", product_kind="RAW_MATERIAL",
                base_unit=lb, costing_method="WEIGHTED_AVERAGE")
l1 = Batch(batch_code="L-001", product=verde, batch_type="PURCHASED",
           initial_quantity=D("100"), unit=lb)
l2 = Batch(batch_code="L-002", product=verde, batch_type="PURCHASED",
           initial_quantity=D("50"), unit=lb)
blend = Batch(batch_code="L-003", product=verde, batch_type="PRODUCED",
              initial_quantity=D("150"), unit=lb)
blend.parent_links = [BatchLineage(parent_batch=l1, quantity_consumed=D("100"), unit=lb),
                      BatchLineage(parent_batch=l2, quantity_consumed=D("50"), unit=lb)]
assert len(blend.parent_links) == 2
assert {lk.parent_batch.batch_code for lk in blend.parent_links} == {"L-001", "L-002"}
assert blend in [lk.child_batch for lk in l1.child_links]

# Venta con una linea surtida desde dos lotes: el caso que justifica la tabla.
venta = Sale(sale_number="V-2026-0001", party=finca, channel="RETAIL",
             sale_date=hoy, total=D("180000"), paid_amount=D("80000"))
linea = SaleItem(line_no=1, product=verde, quantity=D("30"), unit=lb,
                 quantity_base=D("30"), unit_price=D("6000"), price_source="PRICE_LIST",
                 subtotal=D("180000"), total=D("180000"))
linea.batch_allocations = [
    SaleItemBatch(batch=l1, quantity=D("18"), unit=lb, quantity_base=D("18"),
                  unit_cost=D("3000"), total_cost=D("54000")),
    SaleItemBatch(batch=l2, quantity=D("12"), unit=lb, quantity_base=D("12"),
                  unit_cost=D("3200"), total_cost=D("38400")),
]
venta.items = [linea]
assert venta.balance_due == D("100000"), venta.balance_due
assert venta.is_fully_paid is False
assert linea.allocated_quantity_base == D("30")
assert linea.is_batch_allocation_balanced is True, "invariante de asignacion de lotes"
assert venta.items[0].sale is venta, "navegacion inversa sale<->items rota"

# Y el caso que la invariante debe rechazar.
linea.batch_allocations.pop()
assert linea.is_batch_allocation_balanced is False

print("[OK] Grafo de objetos navegable en ambos sentidos.")
print("[OK] Tercero con dos roles, linaje de blend y venta multi-lote correctos.")
print("[OK] Invariante de asignacion de lotes detecta el descuadre.")
