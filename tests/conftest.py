import pytest
from datetime import date
from decimal import Decimal
from sqlalchemy import text

from app import create_app
from app.extensions import db
from app.models import (
    Address,
    InventoryLocation,
    Party,
    PartyRole,
    Product,
    Purchase,
    PurchaseItem,
    UnitOfMeasure,
)


@pytest.fixture
def app():
    app = create_app("testing")

    with app.app_context():
        with db.engine.begin() as connection:
            connection.execute(text("CREATE EXTENSION IF NOT EXISTS btree_gist"))
        db.drop_all()
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()


@pytest.fixture
def session(app):
    return db.session


@pytest.fixture
def lb(session):
    unit = UnitOfMeasure(
        code="LB",
        name="Libra",
        dimension="MASS",
        is_base_for_dimension=True,
    )
    session.add(unit)
    session.flush()
    return unit


@pytest.fixture
def warehouse(session):
    location = InventoryLocation(
        code="BOD-01",
        name="Bodega principal",
        location_type="WAREHOUSE",
    )
    session.add(location)
    session.flush()
    return location


@pytest.fixture
def supplier(session):
    party = Party(
        party_type="NATURAL",
        document_type="CC",
        document_number="100000001",
        legal_name="Proveedor de prueba",
        first_name="Proveedor",
        last_name="Prueba",
    )
    party.party_roles = [PartyRole(role_code="SUPPLIER", valid_from=date.today())]
    session.add(party)
    session.flush()
    return party


@pytest.fixture
def customer(session):
    party = Party(
        party_type="NATURAL",
        document_type="CC",
        document_number="100000002",
        legal_name="Cliente de prueba",
        first_name="Cliente",
        last_name="Prueba",
    )
    party.party_roles = [PartyRole(role_code="CUSTOMER", valid_from=date.today())]
    session.add(party)
    session.flush()
    return party


@pytest.fixture
def coffee_product(session, lb):
    product = Product(
        sku="TEST-COFFEE",
        name="Cafe de prueba",
        product_kind="RAW_MATERIAL",
        base_unit_id=lb.id,
        is_purchasable=True,
        is_sellable=True,
        costing_method="WEIGHTED_AVERAGE",
    )
    session.add(product)
    session.flush()
    return product


@pytest.fixture
def confirmed_purchase(session, supplier, coffee_product, lb, warehouse):
    purchase = Purchase(
        purchase_number="C-TEST-001",
        party_id=supplier.id,
        purchase_type="COFFEE_GROWER",
        purchase_date=date.today(),
        status="CONFIRMED",
        destination_location_id=warehouse.id,
        currency="COP",
    )
    purchase.items = [
        PurchaseItem(
            line_no=1,
            product_id=coffee_product.id,
            quantity=Decimal("100"),
            unit_id=lb.id,
            quantity_base=Decimal("100"),
            unit_price=Decimal("3000"),
            subtotal=Decimal("300000"),
            total=Decimal("300000"),
            landed_unit_cost=Decimal("3000"),
        )
    ]
    session.add(purchase)
    session.flush()
    return purchase