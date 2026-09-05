"""Modelos del ERP Densa Niebla.

50 tablas en 13 modulos, segun el ERD logico v1.0.

Este paquete importa TODOS los modelos. Alembic solo detecta las tablas que
esten registradas en ``Base.metadata`` al momento de ejecutar ``flask db
migrate``; un modelo que exista en un archivo pero no se importe aqui es un
modelo invisible para las migraciones. Es el error mas frecuente al arrancar un
proyecto con Flask-Migrate.

El orden de importacion sigue el orden de dependencias de la seccion 17 del ERD.
"""

from __future__ import annotations

# --- Infraestructura -------------------------------------------------------
from app.models.base import (
    NAMING_CONVENTION,
    Base,
    daterange_expr,
    enum_check,
    fraction_check,
    metadata_obj,
    positive_check,
    validity_check,
)
from app.models.mixins import ActiveMixin, AuditMixin, TimestampMixin, ValidityMixin

# --- 1. Seguridad ----------------------------------------------------------
from app.models.user import ROLE_CODES, Role, User, UserRole

# --- 2. Terceros -----------------------------------------------------------
from app.models.party import (
    ADDRESS_TYPES,
    DOCUMENT_TYPES,
    PARTY_ROLE_CODES,
    PARTY_TYPES,
    TAX_REGIMES,
    Address,
    Party,
    PartyContact,
    PartyRole,
)

# --- 3. Productos, unidades e impuestos ------------------------------------
from app.models.unit import UNIT_DIMENSIONS, UnitConversion, UnitOfMeasure
from app.models.tax import TAX_TYPES, Tax
from app.models.product import (
    COSTING_METHODS,
    GRIND_TYPES,
    PROCESS_METHODS,
    PRODUCT_KINDS,
    ROAST_LEVELS,
    CoffeeProfile,
    Product,
    ProductCategory,
)

# --- 4. Precios y comisiones ----------------------------------------------
from app.models.price import (
    PARTY_PRICE_RULE_TYPES,
    PRICE_LIST_CHANNELS,
    PartyPriceRule,
    PriceList,
    PriceListItem,
)
from app.models.intermediary import (
    FEE_CALCULATION_BASES,
    FEE_ENTRY_STATUSES,
    IntermediaryFeeEntry,
    IntermediaryFeeRule,
)

# --- 5. Compras ------------------------------------------------------------
from app.models.purchase import (
    PURCHASE_PAYMENT_STATUSES,
    PURCHASE_STATUSES,
    PURCHASE_TYPES,
    SUPPLIER_DOCUMENT_TYPES,
    Purchase,
    PurchaseItem,
)

# --- 6. Inventario y lotes -------------------------------------------------
from app.models.inventory import (
    LOCATION_TYPES,
    MOVEMENT_REASON_CODES,
    MOVEMENT_REFERENCE_TYPES,
    MOVEMENT_TYPES,
    MOVEMENT_TYPES_IN,
    MOVEMENT_TYPES_OUT,
    InventoryBalance,
    InventoryLocation,
    InventoryMovement,
)
from app.models.batch import (
    BATCH_STATUSES,
    BATCH_TYPES,
    HARVEST_PERIODS,
    Batch,
    BatchLineage,
)

# --- 7. Produccion ---------------------------------------------------------
from app.models.production import (
    EXECUTOR_TYPES,
    OUTPUT_KINDS,
    PROCESS_EXECUTION_STATUSES,
    PRODUCTION_ORDER_STATUSES,
    PRODUCTION_PROCESS_CODES,
    WASTE_COST_TREATMENTS,
    WASTE_TYPES,
    ProcessExecution,
    ProductionInput,
    ProductionOrder,
    ProductionOutput,
    ProductionProcess,
    ProductionWaste,
)

# --- 8. Costos -------------------------------------------------------------
from app.models.cost import (
    ALLOCATION_BASES,
    CALCULATION_BASES,
    COST_EXECUTOR_TYPES,
    COST_NATURES,
    COST_OBJECT_TYPES,
    COST_RULE_APPLIES_TO,
    CostCategory,
    CostEntry,
    CostRule,
)

# --- 9. Ventas y pagos -----------------------------------------------------
from app.models.sale import (
    PRICE_SOURCES,
    SALE_CHANNELS,
    SALE_PAYMENT_STATUSES,
    SALE_STATUSES,
    Sale,
    SaleItem,
    SaleItemBatch,
)
from app.models.payment import (
    PAYMENT_DIRECTIONS,
    PAYMENT_METHODS,
    PAYMENT_STATUSES,
    PAYMENT_TARGET_TYPES,
    Payment,
    PaymentAllocation,
)

# --- 10. Facturacion DIAN --------------------------------------------------
from app.models.invoice import (
    DIAN_ENVIRONMENTS,
    DIAN_STATUSES,
    FISCAL_DOCUMENT_TYPES,
    INVOICE_DOCUMENT_TYPES,
    INVOICE_EVENT_TYPES,
    PAYMENT_FORMS,
    FiscalResolution,
    Invoice,
    InvoiceEvent,
    InvoiceItem,
)

# --- 11. Logistica ---------------------------------------------------------
from app.models.shipment import (
    SHIPMENT_EVENT_TYPES,
    SHIPMENT_STATUSES,
    SHIPMENT_TYPES,
    Shipment,
    ShipmentEvent,
    ShipmentItem,
)

# --- 12. Gastos ------------------------------------------------------------
from app.models.expense import (
    EXPENSE_DOCUMENT_TYPES,
    EXPENSE_NATURES,
    EXPENSE_PAYMENT_METHODS,
    EXPENSE_PAYMENT_STATUSES,
    Expense,
    ExpenseCategory,
)

# --- 13. Configuracion -----------------------------------------------------
from app.models.setting import (
    DOCUMENT_SEQUENCE_CODES,
    INITIAL_APP_SETTINGS,
    SETTING_VALUE_TYPES,
    AppSetting,
    DocumentSequence,
)

# Las 50 clases mapeadas, en el mismo orden de los modulos del ERD.
MODELS: tuple[type[Base], ...] = (
    # Seguridad
    User, Role, UserRole,
    # Terceros
    Party, PartyRole, Address, PartyContact,
    # Productos y unidades
    UnitOfMeasure, UnitConversion, ProductCategory, Tax, Product, CoffeeProfile,
    # Precios y comisiones
    PriceList, PriceListItem, PartyPriceRule,
    IntermediaryFeeRule, IntermediaryFeeEntry,
    # Compras
    Purchase, PurchaseItem,
    # Inventario y lotes
    InventoryLocation, Batch, BatchLineage, InventoryMovement, InventoryBalance,
    # Produccion
    ProductionProcess, ProductionOrder, ProcessExecution,
    ProductionInput, ProductionOutput, ProductionWaste,
    # Costos
    CostCategory, CostRule, CostEntry,
    # Ventas y pagos
    Sale, SaleItem, SaleItemBatch, Payment, PaymentAllocation,
    # Facturacion DIAN
    FiscalResolution, Invoice, InvoiceItem, InvoiceEvent,
    # Logistica
    Shipment, ShipmentItem, ShipmentEvent,
    # Gastos
    ExpenseCategory, Expense,
    # Configuracion
    AppSetting, DocumentSequence,
)

__all__ = [
    # Infraestructura
    "ActiveMixin", "AuditMixin", "Base", "MODELS", "NAMING_CONVENTION",
    "TimestampMixin", "ValidityMixin", "daterange_expr", "enum_check",
    "fraction_check", "metadata_obj", "positive_check", "validity_check",
    # Modelos
    "Address", "AppSetting", "Batch", "BatchLineage", "CoffeeProfile",
    "CostCategory", "CostEntry", "CostRule", "DocumentSequence", "Expense",
    "ExpenseCategory", "FiscalResolution", "IntermediaryFeeEntry",
    "IntermediaryFeeRule", "InventoryBalance", "InventoryLocation",
    "InventoryMovement", "Invoice", "InvoiceEvent", "InvoiceItem", "Party",
    "PartyContact", "PartyPriceRule", "PartyRole", "Payment",
    "PaymentAllocation", "PriceList", "PriceListItem", "ProcessExecution",
    "Product", "ProductCategory", "ProductionInput", "ProductionOrder",
    "ProductionOutput", "ProductionProcess", "ProductionWaste", "Purchase",
    "PurchaseItem", "Role", "Sale", "SaleItem", "SaleItemBatch", "Shipment",
    "ShipmentEvent", "ShipmentItem", "Tax", "UnitConversion", "UnitOfMeasure",
    "User", "UserRole",
    # Catalogos de valores
    "ADDRESS_TYPES", "ALLOCATION_BASES", "BATCH_STATUSES", "BATCH_TYPES",
    "CALCULATION_BASES", "COSTING_METHODS", "COST_EXECUTOR_TYPES",
    "COST_NATURES", "COST_OBJECT_TYPES", "COST_RULE_APPLIES_TO",
    "DIAN_ENVIRONMENTS", "DIAN_STATUSES", "DOCUMENT_SEQUENCE_CODES",
    "INITIAL_APP_SETTINGS",
    "DOCUMENT_TYPES", "EXECUTOR_TYPES", "EXPENSE_DOCUMENT_TYPES",
    "EXPENSE_NATURES", "EXPENSE_PAYMENT_METHODS", "EXPENSE_PAYMENT_STATUSES",
    "FEE_CALCULATION_BASES", "FEE_ENTRY_STATUSES", "FISCAL_DOCUMENT_TYPES",
    "GRIND_TYPES", "HARVEST_PERIODS", "INVOICE_DOCUMENT_TYPES",
    "INVOICE_EVENT_TYPES", "LOCATION_TYPES", "MOVEMENT_REASON_CODES",
    "MOVEMENT_REFERENCE_TYPES", "MOVEMENT_TYPES", "MOVEMENT_TYPES_IN",
    "MOVEMENT_TYPES_OUT", "OUTPUT_KINDS", "PARTY_PRICE_RULE_TYPES",
    "PARTY_ROLE_CODES", "PARTY_TYPES", "PAYMENT_DIRECTIONS", "PAYMENT_FORMS",
    "PAYMENT_METHODS", "PAYMENT_STATUSES", "PAYMENT_TARGET_TYPES",
    "PRICE_LIST_CHANNELS", "PRICE_SOURCES", "PROCESS_EXECUTION_STATUSES",
    "PROCESS_METHODS", "PRODUCTION_ORDER_STATUSES", "PRODUCTION_PROCESS_CODES",
    "PRODUCT_KINDS", "PURCHASE_PAYMENT_STATUSES", "PURCHASE_STATUSES",
    "PURCHASE_TYPES", "ROAST_LEVELS", "ROLE_CODES", "SALE_CHANNELS",
    "SALE_PAYMENT_STATUSES", "SALE_STATUSES", "SETTING_VALUE_TYPES",
    "SHIPMENT_EVENT_TYPES", "SHIPMENT_STATUSES", "SHIPMENT_TYPES",
    "SUPPLIER_DOCUMENT_TYPES", "TAX_REGIMES", "TAX_TYPES", "UNIT_DIMENSIONS",
    "WASTE_COST_TREATMENTS", "WASTE_TYPES",
]
