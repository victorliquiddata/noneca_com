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
            {"id": "BRAND", "value_name": "Noneca"},
            {"id": "SIZE", "value_id": "M"},
            {"id": "MAIN_COLOR", "value_name": "Preto"},
        ]
        assert _get_attr(attrs, "BRAND") == "Noneca"
        assert _get_attr(attrs, "SIZE") == "M"
        assert _get_attr(attrs, "MAIN_COLOR") == "Preto"

    def test_get_attr_not_found(self):
        """Test attribute extraction when key not found."""
        attrs = [{"id": "BRAND", "value_name": "Noneca"}]
        assert _get_attr(attrs, "PANTY_TYPE") is None

    def test_get_attr_empty_attrs(self):
        """Test attribute extraction with empty attributes list."""
        assert _get_attr([], "BRAND") is None

    def test_get_attr_none_attrs(self):
        """Test attribute extraction with None attributes."""
        assert _get_attr(None, "BRAND") is None

    def test_get_attr_value_name_priority(self):
        """Test that value_name takes priority over value_id."""
        attrs = [{"id": "BRAND", "value_name": "Noneca", "value_id": "NONECA_ID"}]
        assert _get_attr(attrs, "BRAND") == "Noneca"

    def test_get_attr_fallback_to_value_id(self):
        """Test fallback to value_id when value_name is None."""
        attrs = [{"id": "SIZE", "value_name": None, "value_id": "P"}]
        assert _get_attr(attrs, "SIZE") == "P"

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
        assert _calculate_discount_percentage(61.7, 50) == 18.96

    def test_calculate_discount_no_discount(self):
        """Test when current price equals original price."""
        assert _calculate_discount_percentage(61.7, 61.7) == 0.0

    def test_calculate_discount_price_increase(self):
        """Test when current price is higher than original."""
        assert _calculate_discount_percentage(45.0, 50.0) == 0.0

    def test_calculate_discount_zero_original(self):
        """Test when original price is zero."""
        assert _calculate_discount_percentage(0, 50) == 0.0

    def test_calculate_discount_none_original(self):
        """Test when original price is None."""
        assert _calculate_discount_percentage(None, 50) == 0.0

    def test_calculate_discount_precision(self):
        """Test discount calculation precision."""
        assert _calculate_discount_percentage(75.0, 61.7) == 17.73


class TestEnrichItem:
    """Test cases for enrich_item function."""

    def test_enrich_item_complete(self):
        """Test enriching item with complete data."""
        raw_item = {
            "id": "MLB1101016456",
            "title": "Noneca - Calcinha Aquendar Vinil - Trans, Cds, Travs, Drags",
            "category_id": "MLB4954",
            "price": 61.7,
            "original_price": 75.0,
            "available_quantity": 26,
            "sold_quantity": 1148,
            "condition": "new",
            "views": 15000,
            "seller_id": "354140329",
            "attributes": [
                {"id": "BRAND", "value_name": "Noneca"},
                {"id": "SIZE", "value_name": "M"},
                {"id": "MAIN_COLOR", "value_name": "Preto"},
                {"id": "PANTY_TYPE", "value_name": "Calcinha"},
                {"id": "GENDER", "value_name": "Trans"},
            ],
        }

        result = enrich_item(raw_item)

        # Basic fields
        assert result["item_id"] == "MLB1101016456"
        assert (
            result["title"]
            == "Noneca - Calcinha Aquendar Vinil - Trans, Cds, Travs, Drags"
        )
        assert result["category_id"] == "MLB4954"
        assert result["current_price"] == 61.7
        assert result["original_price"] == 75.0
        assert result["available_quantity"] == 26
        assert result["sold_quantity"] == 1148
        assert result["condition"] == "new"
        assert result["seller_id"] == "354140329"

        # Extracted attributes
        assert result["brand"] == "Noneca"
        assert result["size"] == "M"
        assert result["color"] == "Preto"
        assert result["gender"] == "Trans"

        # Calculated fields
        assert result["views"] == 15000
        assert result["conversion_rate"] == 0.0765  # 1148/15000
        assert result["discount_percentage"] == 17.73  # (75-61.7)/75*100

        # Timestamps
        assert isinstance(result["created_at"], datetime)
        assert isinstance(result["updated_at"], datetime)

    def test_enrich_item_minimal_data(self):
        """Test enriching item with minimal data."""
        raw_item = {"id": "MLB1234567", "title": "Calcinha Básica"}

        result = enrich_item(raw_item)

        assert result["item_id"] == "MLB1234567"
        assert result["title"] == "Calcinha Básica"
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
        raw_item = {"id": "MLB1234567", "sold_quantity": 10, "views": 0}

        result = enrich_item(raw_item)
        assert result["conversion_rate"] == 0.0

    def test_enrich_item_string_prices(self):
        """Test that string prices are converted to float."""
        raw_item = {"id": "MLB1234567", "price": "61.50", "original_price": "75.90"}

        result = enrich_item(raw_item)
        assert result["current_price"] == 61.5
        assert result["original_price"] == 75.9

    def test_enrich_item_none_prices(self):
        """Test handling of None prices."""
        raw_item = {"id": "MLB1234567", "price": None, "original_price": None}

        result = enrich_item(raw_item)
        assert result["current_price"] == 0.0
        assert result["original_price"] == 0.0

    def test_enrich_item_original_price_defaults_to_current(self):
        """Test that original_price defaults to current price when not provided."""
        raw_item = {"id": "MLB1234567", "price": 45.90}

        result = enrich_item(raw_item)
        assert result["current_price"] == 45.90
        assert result["original_price"] == 45.90
        assert result["discount_percentage"] == 0.0

    def test_enrich_item_timezone_aware_timestamps(self):
        """Test that timestamps are timezone-aware."""
        raw_item = {"id": "MLB1234567"}

        result = enrich_item(raw_item)

        assert result["created_at"].tzinfo == timezone.utc
        assert result["updated_at"].tzinfo == timezone.utc


class TestEnrichItems:
    """Test cases for enrich_items function."""

    def test_enrich_items_multiple(self):
        """Test enriching multiple items."""
        raw_items = [
            {"id": "MLB1101016456", "title": "Calcinha Vinil Trans", "price": 61.7},
            {"id": "MLB1234567", "title": "Calcinha Básica", "price": 35.0},
        ]

        result = enrich_items(raw_items)

        assert len(result) == 2
        assert result[0]["item_id"] == "MLB1101016456"
        assert result[0]["current_price"] == 61.7
        assert result[1]["item_id"] == "MLB1234567"
        assert result[1]["current_price"] == 35.0

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
            {"id": "MLB1101016456", "title": "Calcinha Vinil", "price": 61.7},
            None,
            {"id": "MLB1234567", "title": "Calcinha Básica", "price": 35.0},
        ]

        result = enrich_items(raw_items)

        # Should filter out None items
        assert len(result) == 2
        assert result[0]["item_id"] == "MLB1101016456"
        assert result[1]["item_id"] == "MLB1234567"

    def test_enrich_items_with_empty_items(self):
        """Test enriching list containing empty dict items."""
        raw_items = [
            {"id": "MLB1101016456", "title": "Calcinha Vinil", "price": 61.7},
            {},
            {"id": "MLB1234567", "title": "Calcinha Básica", "price": 35.0},
        ]

        result = enrich_items(raw_items)

        # Should filter out empty items
        assert len(result) == 2
        assert result[0]["item_id"] == "MLB1101016456"
        assert result[1]["item_id"] == "MLB1234567"


@pytest.mark.parametrize(
    "views,sold,expected",
    [
        (15000, 1148, 0.0765),
        (0, 10, 0.0),
        (500, 0, 0.0),
        (1000, 25, 0.025),
    ],
)
def test_conversion_rate_calculations(views, sold, expected):
    """Parameterized test for conversion rate calculations."""
    raw_item = {"id": "MLB1234567", "views": views, "sold_quantity": sold}
    result = enrich_item(raw_item)
    assert result["conversion_rate"] == expected


@pytest.mark.parametrize(
    "original,current,expected",
    [
        (75.0, 61.7, 17.73),
        (50.0, 35.0, 30.0),
        (61.7, 61.7, 0.0),
        (45.0, 50.0, 0.0),  # Price increase
        (0, 50, 0.0),
        (None, 50, 0.0),
    ],
)
def test_discount_calculations(original, current, expected):
    """Parameterized test for discount calculations."""
    raw_item = {"id": "MLB1234567", "price": current, "original_price": original}
    result = enrich_item(raw_item)
    assert result["discount_percentage"] == expected


class TestEdgeCases:
    """Test edge cases and error conditions."""

    def test_malformed_attributes(self):
        """Test handling of malformed attributes."""
        raw_item = {
            "id": "MLB1234567",
            "attributes": [
                {"id": "BRAND"},  # Missing value fields
                {"value_name": "Noneca"},  # Missing id field
                {"id": "SIZE", "value_name": "", "value_id": ""},  # Empty values
                {
                    "id": "MAIN_COLOR",
                    "value_name": "Preto",
                    "value_id": "BLACK",
                },  # Normal
            ],
        }

        result = enrich_item(raw_item)

        assert result["brand"] is None
        assert result["size"] is None
        assert result["color"] == "Preto"

    def test_large_numbers(self):
        """Test handling of large numbers."""
        raw_item = {
            "id": "MLB1234567",
            "price": 999999.99,
            "views": 1000000,
            "sold_quantity": 50000,
        }

        result = enrich_item(raw_item)

        assert result["current_price"] == 999999.99
        assert result["views"] == 1000000
        assert result["conversion_rate"] == 0.05  # 50000/1000000

    def test_unicode_strings(self):
        """Test handling of unicode strings."""
        raw_item = {
            "id": "MLB1234567",
            "title": "Calcinha Renda Açaí",
            "attributes": [{"id": "BRAND", "value_name": "Nonéca"}],
        }

        result = enrich_item(raw_item)

        assert result["title"] == "Calcinha Renda Açaí"
        assert result["brand"] == "Nonéca"

    def test_extreme_precision(self):
        """Test precision handling with extreme decimal places."""
        raw_item = {"id": "MLB1234567", "views": 7, "sold_quantity": 3}

        result = enrich_item(raw_item)

        # 3/7 = 0.4285714285714286, should be rounded to 4 decimal places
        assert result["conversion_rate"] == 0.4286


@pytest.fixture
def sample_raw_items():
    """Fixture providing sample raw items for testing."""
    return [
        {
            "id": "MLB1101016456",
            "title": "Noneca - Calcinha Aquendar Vinil - Trans, Cds, Travs, Drags",
            "category_id": "MLB4954",
            "price": 61.7,
            "original_price": 75.0,
            "available_quantity": 26,
            "sold_quantity": 1148,
            "condition": "new",
            "views": 15000,
            "seller_id": "354140329",
            "attributes": [
                {"id": "BRAND", "value_name": "Noneca"},
                {"id": "SIZE", "value_name": "M"},
                {"id": "MAIN_COLOR", "value_name": "Preto"},
                {"id": "PANTY_TYPE", "value_name": "Calcinha"},
                {"id": "GENDER", "value_name": "Trans"},
            ],
        },
        {
            "id": "MLB1234567",
            "title": "Calcinha Renda Clássica",
            "category_id": "MLB4954",
            "price": 35.0,
            "original_price": 42.0,
            "available_quantity": 15,
            "sold_quantity": 89,
            "condition": "new",
            "views": 890,
            "seller_id": "354140329",
            "attributes": [
                {"id": "BRAND", "value_name": "Noneca"},
                {"id": "SIZE", "value_name": "G"},
                {"id": "MAIN_COLOR", "value_name": "Rosa"},
                {"id": "PANTY_TYPE", "value_name": "Calcinha"},
                {"id": "GENDER", "value_name": "Feminino"},
            ],
        },
    ]


def test_realistic_enrichment_scenario(sample_raw_items):
    """Test enrichment with realistic underwear marketplace data."""
    result = enrich_items(sample_raw_items)

    assert len(result) == 2

    # Vinyl panty checks
    vinyl_panty = result[0]
    assert vinyl_panty["item_id"] == "MLB1101016456"
    assert vinyl_panty["brand"] == "Noneca"
    assert vinyl_panty["size"] == "M"
    assert vinyl_panty["color"] == "Preto"
    assert vinyl_panty["gender"] == "Trans"
    assert vinyl_panty["conversion_rate"] == 0.0765  # 1148/15000
    assert vinyl_panty["discount_percentage"] == 17.73  # (75-61.7)/75*100

    # Lace panty checks
    lace_panty = result[1]
    assert lace_panty["item_id"] == "MLB1234567"
    assert lace_panty["brand"] == "Noneca"
    assert lace_panty["size"] == "G"
    assert lace_panty["color"] == "Rosa"
    assert lace_panty["gender"] == "Feminino"
    assert lace_panty["conversion_rate"] == 0.1  # 89/890
    assert lace_panty["discount_percentage"] == 16.67  # (42-35)/42*100
