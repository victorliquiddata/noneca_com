# tests/test_product_enricher.py
import pytest
from datetime import datetime, timezone
from src.transformers.product_enricher import (
    _get_attr,
    _safe_divide,
    _calculate_discount_percentage,
    enrich_item,
    enrich_items,
)


class TestGetAttr:
    """Test cases for _get_attr helper function."""

    def test_get_attr_success(self):
        """Test successful attribute extraction."""
        attrs = [
            {"id": "BRAND", "value_name": "Nike"},
            {"id": "SIZE", "value_id": "M"},
            {"id": "COLOR", "value_name": "Red"},
        ]

        assert _get_attr(attrs, "BRAND") == "Nike"
        assert _get_attr(attrs, "SIZE") == "M"
        assert _get_attr(attrs, "COLOR") == "Red"

    def test_get_attr_not_found(self):
        """Test attribute extraction when key not found."""
        attrs = [{"id": "BRAND", "value_name": "Nike"}]
        assert _get_attr(attrs, "SIZE") is None

    def test_get_attr_empty_attrs(self):
        """Test attribute extraction with empty attributes list."""
        assert _get_attr([], "BRAND") is None

    def test_get_attr_none_attrs(self):
        """Test attribute extraction with None attributes."""
        assert _get_attr(None, "BRAND") is None

    def test_get_attr_value_name_priority(self):
        """Test that value_name takes priority over value_id."""
        attrs = [{"id": "BRAND", "value_name": "Nike", "value_id": "NIKE_ID"}]
        assert _get_attr(attrs, "BRAND") == "Nike"

    def test_get_attr_fallback_to_value_id(self):
        """Test fallback to value_id when value_name is None."""
        attrs = [{"id": "BRAND", "value_name": None, "value_id": "NIKE_ID"}]
        assert _get_attr(attrs, "BRAND") == "NIKE_ID"

    def test_get_attr_both_none(self):
        """Test when both value_name and value_id are None."""
        attrs = [{"id": "BRAND", "value_name": None, "value_id": None}]
        assert _get_attr(attrs, "BRAND") is None


class TestSafeDivide:
    """Test cases for _safe_divide helper function."""

    def test_safe_divide_normal(self):
        """Test normal division."""
        assert _safe_divide(10, 2) == 5.0
        assert _safe_divide(7, 3, precision=2) == 2.33

    def test_safe_divide_by_zero(self):
        """Test division by zero."""
        assert _safe_divide(10, 0) == 0.0

    def test_safe_divide_zero_numerator(self):
        """Test zero numerator."""
        assert _safe_divide(0, 5) == 0.0

    def test_safe_divide_negative_numbers(self):
        """Test division with negative numbers."""
        assert _safe_divide(-10, 2) == -5.0
        assert _safe_divide(10, -2) == -5.0

    def test_safe_divide_precision(self):
        """Test precision parameter."""
        assert _safe_divide(1, 3, precision=2) == 0.33
        assert _safe_divide(1, 3, precision=4) == 0.3333


class TestCalculateDiscountPercentage:
    """Test cases for _calculate_discount_percentage helper function."""

    def test_calculate_discount_normal(self):
        """Test normal discount calculation."""
        assert _calculate_discount_percentage(100, 80) == 20.0
        assert _calculate_discount_percentage(200, 150) == 25.0

    def test_calculate_discount_no_discount(self):
        """Test when current price equals original price."""
        assert _calculate_discount_percentage(100, 100) == 0.0

    def test_calculate_discount_price_increase(self):
        """Test when current price is higher than original."""
        assert _calculate_discount_percentage(100, 120) == 0.0

    def test_calculate_discount_zero_original(self):
        """Test when original price is zero."""
        assert _calculate_discount_percentage(0, 50) == 0.0

    def test_calculate_discount_none_original(self):
        """Test when original price is None."""
        assert _calculate_discount_percentage(None, 50) == 0.0

    def test_calculate_discount_precision(self):
        """Test discount calculation precision."""
        assert _calculate_discount_percentage(150, 100) == 33.33


class TestEnrichItem:
    """Test cases for enrich_item function."""

    def test_enrich_item_complete(self):
        """Test enriching item with complete data."""
        raw_item = {
            "id": "MLA123456",
            "title": "iPhone 13 Pro",
            "category_id": "MLA1055",
            "price": 1000,
            "original_price": 1200,
            "available_quantity": 5,
            "sold_quantity": 15,
            "condition": "new",
            "views": 500,
            "seller_id": "SELLER123",
            "attributes": [
                {"id": "BRAND", "value_name": "Apple"},
                {"id": "SIZE", "value_name": "128GB"},
                {"id": "COLOR", "value_name": "Blue"},
                {"id": "GENDER", "value_name": "Unisex"},
            ],
        }

        result = enrich_item(raw_item)

        # Basic fields
        assert result["item_id"] == "MLA123456"
        assert result["title"] == "iPhone 13 Pro"
        assert result["category_id"] == "MLA1055"
        assert result["current_price"] == 1000.0
        assert result["original_price"] == 1200.0
        assert result["available_quantity"] == 5
        assert result["sold_quantity"] == 15
        assert result["condition"] == "new"
        assert result["seller_id"] == "SELLER123"

        # Extracted attributes
        assert result["brand"] == "Apple"
        assert result["size"] == "128GB"
        assert result["color"] == "Blue"
        assert result["gender"] == "Unisex"

        # Calculated fields
        assert result["views"] == 500
        assert result["conversion_rate"] == 0.03  # 15/500
        assert result["discount_percentage"] == 16.67  # (1200-1000)/1200*100

        # Timestamps
        assert isinstance(result["created_at"], datetime)
        assert isinstance(result["updated_at"], datetime)

    def test_enrich_item_minimal_data(self):
        """Test enriching item with minimal data."""
        raw_item = {"id": "MLA123456", "title": "Test Item"}

        result = enrich_item(raw_item)

        assert result["item_id"] == "MLA123456"
        assert result["title"] == "Test Item"
        assert result["current_price"] == 0.0
        assert result["original_price"] == 0.0
        assert result["conversion_rate"] == 0.0
        assert result["discount_percentage"] == 0.0
        assert result["brand"] is None
        assert result["views"] == 0

    def test_enrich_item_empty_dict(self):
        """Test enriching empty item."""
        result = enrich_item({})
        assert result == {}

    def test_enrich_item_none(self):
        """Test enriching None item."""
        result = enrich_item(None)
        assert result == {}

    def test_enrich_item_no_views_no_division_error(self):
        """Test that zero views doesn't cause division error."""
        raw_item = {"id": "MLA123456", "sold_quantity": 10, "views": 0}

        result = enrich_item(raw_item)
        assert result["conversion_rate"] == 0.0

    def test_enrich_item_string_prices(self):
        """Test that string prices are converted to float."""
        raw_item = {"id": "MLA123456", "price": "100.50", "original_price": "120.75"}

        result = enrich_item(raw_item)
        assert result["current_price"] == 100.5
        assert result["original_price"] == 120.75

    def test_enrich_item_none_prices(self):
        """Test handling of None prices."""
        raw_item = {"id": "MLA123456", "price": None, "original_price": None}

        result = enrich_item(raw_item)
        assert result["current_price"] == 0.0
        assert result["original_price"] == 0.0

    def test_enrich_item_original_price_defaults_to_current(self):
        """Test that original_price defaults to current price when not provided."""
        raw_item = {"id": "MLA123456", "price": 100}

        result = enrich_item(raw_item)
        assert result["current_price"] == 100.0
        assert result["original_price"] == 100.0
        assert result["discount_percentage"] == 0.0

    def test_enrich_item_timezone_aware_timestamps(self):
        """Test that timestamps are timezone-aware."""
        raw_item = {"id": "MLA123456"}

        result = enrich_item(raw_item)

        assert result["created_at"].tzinfo == timezone.utc
        assert result["updated_at"].tzinfo == timezone.utc


class TestEnrichItems:
    """Test cases for enrich_items function."""

    def test_enrich_items_multiple(self):
        """Test enriching multiple items."""
        raw_items = [
            {"id": "MLA123456", "title": "Item 1", "price": 100},
            {"id": "MLA789012", "title": "Item 2", "price": 200},
        ]

        result = enrich_items(raw_items)

        assert len(result) == 2
        assert result[0]["item_id"] == "MLA123456"
        assert result[0]["current_price"] == 100.0
        assert result[1]["item_id"] == "MLA789012"
        assert result[1]["current_price"] == 200.0

    def test_enrich_items_empty_list(self):
        """Test enriching empty list."""
        result = enrich_items([])
        assert result == []

    def test_enrich_items_none_input(self):
        """Test enriching None input."""
        result = enrich_items(None)
        assert result == []

    def test_enrich_items_with_none_items(self):
        """Test enriching list containing None items."""
        raw_items = [
            {"id": "MLA123456", "title": "Item 1", "price": 100},
            None,
            {"id": "MLA789012", "title": "Item 2", "price": 200},
        ]

        result = enrich_items(raw_items)

        # Should filter out None items
        assert len(result) == 2
        assert result[0]["item_id"] == "MLA123456"
        assert result[1]["item_id"] == "MLA789012"

    def test_enrich_items_with_empty_items(self):
        """Test enriching list containing empty dict items."""
        raw_items = [
            {"id": "MLA123456", "title": "Item 1", "price": 100},
            {},
            {"id": "MLA789012", "title": "Item 2", "price": 200},
        ]

        result = enrich_items(raw_items)

        # Should filter out empty items
        assert len(result) == 2
        assert result[0]["item_id"] == "MLA123456"
        assert result[1]["item_id"] == "MLA789012"


@pytest.mark.parametrize(
    "views,sold,expected",
    [
        (100, 5, 0.05),
        (0, 10, 0.0),
        (50, 0, 0.0),
        (1000, 25, 0.025),
    ],
)
def test_conversion_rate_calculations(views, sold, expected):
    """Parameterized test for conversion rate calculations."""
    raw_item = {"id": "MLA123456", "views": views, "sold_quantity": sold}

    result = enrich_item(raw_item)
    assert result["conversion_rate"] == expected


@pytest.mark.parametrize(
    "original,current,expected",
    [
        (100, 80, 20.0),
        (200, 150, 25.0),
        (100, 100, 0.0),
        (100, 120, 0.0),
        (0, 50, 0.0),
        (None, 50, 0.0),
    ],
)
def test_discount_calculations(original, current, expected):
    """Parameterized test for discount calculations."""
    raw_item = {"id": "MLA123456", "price": current, "original_price": original}

    result = enrich_item(raw_item)
    assert result["discount_percentage"] == expected


class TestEdgeCases:
    """Test edge cases and error conditions."""

    def test_malformed_attributes(self):
        """Test handling of malformed attributes."""
        raw_item = {
            "id": "MLA123456",
            "attributes": [
                {"id": "BRAND"},  # Missing value fields
                {"value_name": "Nike"},  # Missing id field
                {"id": "SIZE", "value_name": "", "value_id": ""},  # Empty values
                {"id": "COLOR", "value_name": "Red", "value_id": "RED_ID"},  # Normal
            ],
        }

        result = enrich_item(raw_item)

        assert result["brand"] is None  # Missing value fields
        assert result["size"] is None  # Empty values
        assert result["color"] == "Red"  # Normal case

    def test_large_numbers(self):
        """Test handling of large numbers."""
        raw_item = {
            "id": "MLA123456",
            "price": 999999999.99,
            "views": 1000000000,
            "sold_quantity": 500000,
        }

        result = enrich_item(raw_item)

        assert result["current_price"] == 999999999.99
        assert result["views"] == 1000000000
        assert result["conversion_rate"] == 0.0005  # 500000/1000000000

    def test_unicode_strings(self):
        """Test handling of unicode strings."""
        raw_item = {
            "id": "MLA123456",
            "title": "Café Møcha ñiño 中文",
            "attributes": [{"id": "BRAND", "value_name": "Niñø Brandé"}],
        }

        result = enrich_item(raw_item)

        assert result["title"] == "Café Møcha ñiño 中文"
        assert result["brand"] == "Niñø Brandé"

    def test_extreme_precision(self):
        """Test precision handling with extreme decimal places."""
        raw_item = {"id": "MLA123456", "views": 7, "sold_quantity": 3}

        result = enrich_item(raw_item)

        # 3/7 = 0.4285714285714286, should be rounded to 4 decimal places
        assert result["conversion_rate"] == 0.4286


@pytest.fixture
def sample_raw_items():
    """Fixture providing sample raw items for testing."""
    return [
        {
            "id": "MLA123456",
            "title": "iPhone 13 Pro Max 256GB",
            "category_id": "MLA1055",
            "price": 1100,
            "original_price": 1299,
            "available_quantity": 3,
            "sold_quantity": 47,
            "condition": "new",
            "views": 2350,
            "seller_id": "SELLER123",
            "attributes": [
                {"id": "BRAND", "value_name": "Apple"},
                {"id": "SIZE", "value_name": "256GB"},
                {"id": "COLOR", "value_name": "Sierra Blue"},
            ],
        },
        {
            "id": "MLA789012",
            "title": "Samsung Galaxy S23 Ultra",
            "category_id": "MLA1055",
            "price": 950,
            "original_price": 1200,
            "available_quantity": 1,
            "sold_quantity": 23,
            "condition": "used",
            "views": 890,
            "seller_id": "SELLER456",
            "attributes": [
                {"id": "BRAND", "value_name": "Samsung"},
                {"id": "SIZE", "value_name": "512GB"},
                {"id": "COLOR", "value_name": "Phantom Black"},
            ],
        },
    ]


def test_realistic_enrichment_scenario(sample_raw_items):
    """Test enrichment with realistic marketplace data."""
    result = enrich_items(sample_raw_items)

    assert len(result) == 2

    # iPhone item checks
    iphone = result[0]
    assert iphone["item_id"] == "MLA123456"
    assert iphone["brand"] == "Apple"
    assert iphone["size"] == "256GB"
    assert iphone["color"] == "Sierra Blue"
    assert iphone["conversion_rate"] == 0.02  # 47/2350
    assert iphone["discount_percentage"] == 15.32  # (1299-1100)/1299*100

    # Samsung item checks
    samsung = result[1]
    assert samsung["item_id"] == "MLA789012"
    assert samsung["brand"] == "Samsung"
    assert samsung["conversion_rate"] == 0.0258  # 23/890
    assert samsung["discount_percentage"] == 20.83  # (1200-950)/1200*100
