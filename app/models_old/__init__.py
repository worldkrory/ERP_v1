"""Registro central de modelos SQLAlchemy del ERP Densa Niebla.

Alembic solo detecta los modelos que hayan sido importados. Cada módulo nuevo
debe importarse aquí, o `flask db migrate` generará una migración vacía.

Se irán activando conforme se definan, siguiendo el ERD lógico aprobado:

    from app.models.user import User, Role
    from app.models.party import Party, PartyRole, Address
    from app.models.product import Product, UnitOfMeasure, UnitConversion
    from app.models.price import PriceList, PriceListItem, PartyPriceRule
    from app.models.sale import Sale, SaleItem, SaleItemBatch, Payment
    from app.models.inventory import (
        InventoryLocation, Batch, InventoryMovement,
    )
    from app.models.production import (
        ProductionOrder, ProductionProcess, ProcessExecution,
        ProductionInput, ProductionOutput, Waste,
    )
    from app.models.cost import CostRule, CostEntry
    from app.models.expense import Expense
    from app.models.invoice import Invoice, InvoiceItem
    from app.models.shipment import Shipment
"""

__all__ = []
