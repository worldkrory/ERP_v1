from __future__ import annotations

from decimal import Decimal
from unittest.mock import Mock

import pytest

from app.models.product import Product
from app.services.costing import CostingError, effective_costing_method
from app.services.inventory_service import InventoryError
from app.services.sale_services import SaleError
from app.services.units import UnitConversionError, convert_quantity, get_conversion_factor


class EmptySession:
    def scalars(self, statement):
        result = Mock()
        result.all.return_value = []
        return result


class MissingSettingSession:
    def scalar(self, statement):
        return None


def test_same_unit_conversion_does_not_need_database():
    assert convert_quantity(None, "30", 10, 10) == Decimal("30")
    assert get_conversion_factor(None, 10, 10) == Decimal("1")


def test_negative_quantity_is_rejected():
    with pytest.raises(UnitConversionError):
        convert_quantity(None, "-1", 10, 10)


def test_missing_conversion_is_explicit():
    with pytest.raises(UnitConversionError):
        get_conversion_factor(EmptySession(), 10, 20)


def test_system_costing_uses_weighted_average_fallback():
    product = Product(costing_method="SYSTEM_DEFAULT")
    assert effective_costing_method(MissingSettingSession(), product) == "WEIGHTED_AVERAGE"


def test_invalid_global_costing_method_is_rejected():
    setting = Mock(typed_value="INVALID")
    session = Mock()
    session.scalar.return_value = setting
    with pytest.raises(CostingError):
        effective_costing_method(session, Product(costing_method="SYSTEM_DEFAULT"))


def test_domain_errors_are_value_errors():
    assert issubclass(InventoryError, ValueError)
    assert issubclass(SaleError, ValueError)
