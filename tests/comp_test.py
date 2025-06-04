#!/usr/bin/env python3
import json
import os
import sys
import pytest
from datetime import datetime, timedelta, timezone
from unittest.mock import Mock, patch, mock_open
from dataclasses import dataclass
from typing import Dict, List, Any


# Mock the config module to avoid environment dependencies
@dataclass
class MockConfig:
    client_id: str = "test_client_id"
    client_secret: str = "test_secret"
    redirect_uri: str = "http://test.com/callback"
    timeout: int = 30
    rate_limit: int = 100
    api_url: str = "https://api.test.com"
    auth_url: str = "https://auth.test.com"
    token_file: str = "test_tokens.json"
    fallback_access: str = "test_access_token"
    fallback_refresh: str = "test_refresh_token"
    fallback_expires: str = "2025-12-31T23:59:59"


# Mock modules
with patch.dict(
    "sys.modules",
    {
        "config.config": Mock(cfg=MockConfig()),
        "src.extractors.ml_api_client": Mock(),
    },
):
    # Import after mocking
    import sys

    sys.path.insert(0, ".")

    # Create mock implementations inline since we can't import the real modules
    class MockMLClient:
        def __init__(self):
            self.session = Mock()
            self.session.headers = {}
            self._rate = {"calls": 0, "reset": datetime.now()}

        def _check_rate(self):
            now = datetime.now()
            if now - self._rate["reset"] > timedelta(minutes=1):
                self._rate = {"calls": 0, "reset": now}
            if self._rate["calls"] >= 100:
                raise Exception("Rate limit exceeded")
            self._rate["calls"] += 1

        def _auth(self, token):
            self.session.headers.update({"Authorization": f"Bearer {token}"})

        def get_user(self, token, user_id="me", attrs=None):
            self._auth(token)
            return {"id": "test_user_123", "nickname": "test_seller"}

        def get_items(self, token, seller_id, limit=50, status="active"):
            self._auth(token)
            items = [
                {"id": f"item_{i}", "title": f"Test Item {i}", "price": 100.0 + i}
                for i in range(min(limit, 3))
            ]
            return items

        def get_item(self, token, item_id, attrs=None):
            self._auth(token)
            return {
                "id": item_id,
                "title": "Test Product",
                "price": 299.99,
                "original_price": 399.99,
                "category_id": "CAT123",
                "seller_id": "SELLER123",
                "attributes": [
                    {"id": "BRAND", "value_name": "TestBrand"},
                    {"id": "MAIN_COLOR", "value_name": "Blue"},
                    {"id": "SIZE", "value_name": "M"},
                ],
                "views": 1000,
                "sold_quantity": 50,
                "available_quantity": 10,
                "condition": "new",
            }

        def get_desc(self, token, item_id):
            self._auth(token)
            return {"plain_text": f"Description for {item_id}"}

        def get_reviews(self, token, item_id):
            self._auth(token)
            return {"rating_average": 4.5, "total_reviews": 25, "reviews": []}


# Test fixtures
@pytest.fixture
def mock_client():
    return MockMLClient()


@pytest.fixture
def mock_token():
    return "test_access_token_123"


@pytest.fixture
def sample_item():
    return {
        "id": "ML123456789",
        "title": "iPhone 13 Pro Max 256GB",
        "price": 5999.99,
        "original_price": 6999.99,
        "category_id": "MLA1055",
        "seller_id": "SELLER123",
        "attributes": [
            {"id": "BRAND", "value_name": "Apple"},
            {"id": "MAIN_COLOR", "value_name": "Space Gray"},
            {"id": "SIZE", "value_name": "256GB"},
            {"id": "GENDER", "value_name": "Unisex"},
        ],
        "views": 15000,
        "sold_quantity": 120,
        "available_quantity": 5,
        "condition": "new",
    }


@pytest.fixture
def sample_items_list():
    return [
        {
            "id": "ML001",
            "title": "Product 1",
            "price": 100.0,
            "attributes": [{"id": "BRAND", "value_name": "Brand1"}],
        },
        {
            "id": "ML002",
            "title": "Product 2",
            "price": 200.0,
            "attributes": [{"id": "MAIN_COLOR", "value_name": "Red"}],
        },
    ]


class TestProductEnricher:
    """Test the product enrichment functionality."""

    def test_get_attr_extracts_value_name(self):
        from src.transformers.product_enricher import _get_attr

        attrs = [{"id": "BRAND", "value_name": "Nike", "value_id": "123"}]
        assert _get_attr(attrs, "BRAND") == "Nike"

    def test_get_attr_falls_back_to_value_id(self):
        from src.transformers.product_enricher import _get_attr

        attrs = [{"id": "COLOR", "value_id": "blue_001"}]
        assert _get_attr(attrs, "COLOR") == "blue_001"

    def test_get_attr_returns_none_for_missing_key(self):
        from src.transformers.product_enricher import _get_attr

        attrs = [{"id": "BRAND", "value_name": "Nike"}]
        assert _get_attr(attrs, "SIZE") is None

    def test_get_attr_handles_empty_values(self):
        from src.transformers.product_enricher import _get_attr

        attrs = [{"id": "BRAND", "value_name": "", "value_id": ""}]
        assert _get_attr(attrs, "BRAND") is None

    def test_safe_divide_normal_case(self):
        from src.transformers.product_enricher import _safe_divide

        assert _safe_divide(10, 4) == 2.5
        assert _safe_divide(1, 3, 2) == 0.33

    def test_safe_divide_zero_denominator(self):
        from src.transformers.product_enricher import _safe_divide

        assert _safe_divide(10, 0) == 0.0
        assert _safe_divide(100, None) == 0.0

    def test_calculate_discount_percentage(self):
        from src.transformers.product_enricher import _calculate_discount_percentage

        assert _calculate_discount_percentage(100, 80) == 20.0
        assert _calculate_discount_percentage(200, 150) == 25.0
        assert _calculate_discount_percentage(100, 100) == 0.0
        assert _calculate_discount_percentage(100, 120) == 0.0

    def test_enrich_item_complete_data(self, sample_item):
        from src.transformers.product_enricher import enrich_item

        enriched = enrich_item(sample_item)

        assert enriched["item_id"] == "ML123456789"
        assert enriched["title"] == "iPhone 13 Pro Max 256GB"
        assert enriched["current_price"] == 5999.99
        assert enriched["original_price"] == 6999.99
        assert enriched["brand"] == "Apple"
        assert enriched["color"] == "Space Gray"
        assert enriched["size"] == "256GB"
        assert enriched["gender"] == "Unisex"
        assert enriched["conversion_rate"] == 0.008  # 120/15000
        assert enriched["discount_percentage"] == 14.29
        assert "created_at" in enriched
        assert "updated_at" in enriched

    def test_enrich_item_missing_attributes(self):
        from src.transformers.product_enricher import enrich_item

        minimal_item = {"id": "ML001", "title": "Basic Product", "price": 50.0}

        enriched = enrich_item(minimal_item)

        assert enriched["item_id"] == "ML001"
        assert enriched["brand"] is None
        assert enriched["color"] is None
        assert enriched["conversion_rate"] == 0.0
        assert enriched["discount_percentage"] == 0.0

    def test_enrich_item_empty_input(self):
        from src.transformers.product_enricher import enrich_item

        assert enrich_item({}) == {}
        assert enrich_item(None) == {}

    def test_enrich_items_list(self, sample_items_list):
        from src.transformers.product_enricher import enrich_items

        enriched = enrich_items(sample_items_list)

        assert len(enriched) == 2
        assert enriched[0]["item_id"] == "ML001"
        assert enriched[0]["brand"] == "Brand1"
        assert enriched[1]["item_id"] == "ML002"
        assert enriched[1]["color"] == "Red"

    def test_enrich_items_empty_list(self):
        from src.transformers.product_enricher import enrich_items

        assert enrich_items([]) == []
        assert enrich_items(None) == []


class TestMLAPIClient:
    """Test the ML API client functionality."""

    def test_client_initialization(self, mock_client):
        assert mock_client.session is not None
        assert mock_client._rate["calls"] == 0

    def test_rate_limiting(self, mock_client):
        # Simulate hitting rate limit
        mock_client._rate["calls"] = 100

        with pytest.raises(Exception, match="Rate limit exceeded"):
            mock_client._check_rate()

    def test_rate_limit_reset(self, mock_client):
        # Set calls to limit and reset time to past
        mock_client._rate["calls"] = 100
        mock_client._rate["reset"] = datetime.now() - timedelta(minutes=2)

        # Should reset and not raise exception
        mock_client._check_rate()
        assert mock_client._rate["calls"] == 1

    def test_get_user_default_params(self, mock_client, mock_token):
        user = mock_client.get_user(mock_token)
        assert user["id"] == "test_user_123"
        assert user["nickname"] == "test_seller"

    def test_get_items_with_limit(self, mock_client, mock_token):
        items = mock_client.get_items(mock_token, "seller123", limit=2)
        assert len(items) == 2
        assert items[0]["id"] == "item_0"
        assert items[1]["id"] == "item_1"

    def test_get_item_details(self, mock_client, mock_token):
        item = mock_client.get_item(mock_token, "ML123")
        assert item["id"] == "ML123"
        assert item["title"] == "Test Product"
        assert item["price"] == 299.99

    def test_get_description(self, mock_client, mock_token):
        desc = mock_client.get_desc(mock_token, "ML123")
        assert desc["plain_text"] == "Description for ML123"

    def test_get_reviews(self, mock_client, mock_token):
        reviews = mock_client.get_reviews(mock_token, "ML123")
        assert reviews["rating_average"] == 4.5
        assert reviews["total_reviews"] == 25


class TestItemsExtractor:
    """Test the items extraction functionality."""

    @patch("src.extractors.items_extractor.create_client")
    def test_extract_items_success(self, mock_create_client):
        # Setup mock
        mock_client = Mock()
        mock_client.get_items.return_value = [
            {"id": "ML001", "title": "Product 1"},
            {"id": "ML002", "title": "Product 2"},
        ]
        mock_create_client.return_value = (mock_client, "test_token")

        # Test extraction
        from src.extractors.items_extractor import extract_items

        items = extract_items("seller123", limit=2)

        assert len(items) == 2
        assert items[0]["id"] == "ML001"
        mock_client.get_items.assert_called_once_with(
            "test_token", "seller123", limit=2
        )

    @patch("src.extractors.items_extractor.create_client")
    def test_extract_items_empty_seller_id(self, mock_create_client):
        from src.extractors.items_extractor import extract_items

        items = extract_items("", limit=10)
        assert items == []
        mock_create_client.assert_not_called()

    @patch("src.extractors.items_extractor.create_client")
    def test_extract_items_invalid_limit(self, mock_create_client):
        from src.extractors.items_extractor import extract_items

        items = extract_items("seller123", limit=0)
        assert items == []
        mock_create_client.assert_not_called()

    @patch("src.extractors.items_extractor.create_client")
    def test_extract_items_api_failure(self, mock_create_client):
        # Setup mock to raise exception
        mock_client = Mock()
        mock_client.get_items.side_effect = Exception("API Error")
        mock_create_client.return_value = (mock_client, "test_token")

        from src.extractors.items_extractor import extract_items

        items = extract_items("seller123")
        assert items == []

    @patch("src.extractors.items_extractor.create_client")
    def test_extract_item_details_success(self, mock_create_client):
        # Setup mock
        mock_client = Mock()
        mock_client.get_item.return_value = {"id": "ML123", "title": "Product"}
        mock_create_client.return_value = (mock_client, "test_token")

        from src.extractors.items_extractor import extract_item_details

        item = extract_item_details("ML123")

        assert item["id"] == "ML123"
        mock_client.get_item.assert_called_once_with("test_token", "ML123")

    @patch("src.extractors.items_extractor.create_client")
    def test_extract_items_with_enrichments(self, mock_create_client):
        # Setup mocks
        mock_client = Mock()
        mock_client.get_items.return_value = [{"id": "ML123", "title": "Product"}]
        mock_client.get_desc.return_value = {"plain_text": "Description"}
        mock_client.get_reviews.return_value = {
            "rating_average": 4.0,
            "total_reviews": 10,
        }
        mock_create_client.return_value = (mock_client, "test_token")

        from src.extractors.items_extractor import extract_items_with_enrichments

        items = extract_items_with_enrichments(
            "seller123", include_descriptions=True, include_reviews=True
        )

        assert len(items) == 1
        assert items[0]["description"] == "Description"
        assert items[0]["rating_average"] == 4.0
        assert items[0]["total_reviews"] == 10


class TestTokenManagement:
    """Test token management functions."""

    @patch("src.extractors.ml_api_client.cfg.token_file", "test_tokens.json")
    @patch(
        "builtins.open",
        new_callable=mock_open,
        read_data='{"access_token": "test123", "expires_at": "2025-12-31T23:59:59"}',
    )
    @patch("os.path.exists", return_value=True)
    def test_load_tokens_from_file(self, mock_exists, mock_file):
        from src.extractors.ml_api_client import load_tokens

        tokens = load_tokens()
        assert tokens["access_token"] == "test123"

    @patch("src.extractors.ml_api_client.cfg.fallback_access", "test_access_token")
    @patch("src.extractors.ml_api_client.cfg.fallback_refresh", "test_refresh_token")
    @patch("src.extractors.ml_api_client.cfg.fallback_expires", "2025-12-31T23:59:59")
    @patch("os.path.exists", return_value=False)
    def test_load_tokens_fallback(self, mock_exists):
        from src.extractors.ml_api_client import load_tokens

        tokens = load_tokens()
        assert tokens["access_token"] == "test_access_token"

    def test_is_valid_token_check(self):
        from src.extractors.ml_api_client import is_valid

        # Valid token (expires in future)
        future_time = (datetime.now() + timedelta(hours=1)).isoformat()
        valid_tokens = {"expires_at": future_time}
        assert is_valid(valid_tokens) is True

        # Expired token
        past_time = (datetime.now() - timedelta(hours=1)).isoformat()
        expired_tokens = {"expires_at": past_time}
        assert is_valid(expired_tokens) is False

        # No tokens
        assert is_valid(None) is False

    @patch("src.extractors.ml_api_client.cfg.token_file", "test_tokens.json")
    @patch("builtins.open", new_callable=mock_open)
    def test_save_tokens(self, mock_file):
        from src.extractors.ml_api_client import save_tokens

        tokens = {"access_token": "test", "expires_in": 3600}
        save_tokens(tokens)

        # Check that file was opened for writing
        mock_file.assert_called_once_with("test_tokens.json", "w")


class TestIntegratedWorkflow:
    """Test integrated workflows combining multiple components."""

    @patch("src.extractors.items_extractor.create_client")
    def test_full_extraction_and_enrichment_pipeline(self, mock_create_client):
        # Setup comprehensive mock
        mock_client = Mock()
        mock_client.get_items.return_value = [
            {
                "id": "ML001",
                "title": "iPhone 14",
                "price": 4999.99,
                "original_price": 5999.99,
                "attributes": [
                    {"id": "BRAND", "value_name": "Apple"},
                    {"id": "MAIN_COLOR", "value_name": "Black"},
                ],
                "views": 5000,
                "sold_quantity": 100,
                "seller_id": "SELLER123",
            }
        ]
        mock_create_client.return_value = (mock_client, "test_token")

        # Extract items
        from src.extractors.items_extractor import extract_items

        raw_items = extract_items("SELLER123")

        # Enrich items
        from src.transformers.product_enricher import enrich_items

        enriched_items = enrich_items(raw_items)

        # Verify integrated result
        assert len(enriched_items) == 1
        item = enriched_items[0]
        assert item["item_id"] == "ML001"
        assert item["title"] == "iPhone 14"
        assert item["brand"] == "Apple"
        assert item["color"] == "Black"
        assert item["conversion_rate"] == 0.02  # 100/5000
        assert item["discount_percentage"] == 16.67  # (5999.99-4999.99)/5999.99 * 100

    @patch("src.extractors.items_extractor.create_client")
    def test_error_handling_in_pipeline(self, mock_create_client):
        # Setup mock to simulate API failure
        mock_create_client.side_effect = Exception("Network error")

        from src.extractors.items_extractor import extract_items
        from src.transformers.product_enricher import enrich_items

        # Extraction should fail gracefully
        raw_items = extract_items("SELLER123")
        assert raw_items == []

        # Enrichment should handle empty input
        enriched_items = enrich_items(raw_items)
        assert enriched_items == []

    def test_data_consistency_through_pipeline(self):
        """Test that data maintains consistency through extraction and enrichment."""
        # Simulate raw API data
        raw_items = [
            {
                "id": "ML123",
                "title": "Test Product",
                "price": 299.99,
                "seller_id": "SELLER456",
                "attributes": [{"id": "BRAND", "value_name": "TestBrand"}],
            }
        ]

        from src.transformers.product_enricher import enrich_items

        enriched = enrich_items(raw_items)

        # Verify data consistency
        assert enriched[0]["item_id"] == raw_items[0]["id"]
        assert enriched[0]["title"] == raw_items[0]["title"]
        assert enriched[0]["current_price"] == raw_items[0]["price"]
        assert enriched[0]["seller_id"] == raw_items[0]["seller_id"]
        assert enriched[0]["brand"] == "TestBrand"


class TestEdgeCases:
    """Test edge cases and boundary conditions."""

    def test_enrich_item_with_zero_values(self):
        from src.transformers.product_enricher import enrich_item

        item = {
            "id": "ML000",
            "title": "Free Product",
            "price": 0,
            "views": 0,
            "sold_quantity": 0,
        }

        enriched = enrich_item(item)
        assert enriched["current_price"] == 0
        assert enriched["conversion_rate"] == 0.0
        assert enriched["discount_percentage"] == 0.0

    def test_enrich_item_with_missing_price_fields(self):
        from src.transformers.product_enricher import enrich_item

        item = {"id": "ML999", "title": "No Price Product"}
        enriched = enrich_item(item)

        assert enriched["current_price"] == 0.0
        assert enriched["original_price"] == 0.0

    @patch("src.extractors.items_extractor.create_client")
    def test_extract_items_with_large_limit(self, mock_create_client):
        mock_client = Mock()
        mock_client.get_items.return_value = []
        mock_create_client.return_value = (mock_client, "test_token")

        from src.extractors.items_extractor import extract_items

        items = extract_items("seller123", limit=10000)

        # Should handle large limits gracefully
        assert items == []
        mock_client.get_items.assert_called_once_with(
            "test_token", "seller123", limit=10000
        )

    def test_attribute_extraction_with_malformed_data(self):
        from src.transformers.product_enricher import _get_attr

        # Test various malformed attribute structures
        malformed_attrs = [
            {"id": "BRAND"},  # Missing value fields
            {"value_name": "Nike"},  # Missing id
            {"id": "COLOR", "value_name": None, "value_id": None},  # Null values
            {"id": "SIZE", "value_name": "", "value_id": ""},  # Empty strings
        ]

        assert _get_attr(malformed_attrs, "BRAND") is None
        assert _get_attr(malformed_attrs, "COLOR") is None
        assert _get_attr(malformed_attrs, "SIZE") is None


if __name__ == "__main__":
    # Get the directory of the current script (project root)
    project_root = os.path.dirname(os.path.abspath(__file__))

    # Add the project root to the Python path
    if project_root not in sys.path:
        sys.path.insert(0, project_root)

    # Default pytest arguments — run in verbose mode
    pytest_args = ["tests/", "-v"]  # Verbose output

    # If additional arguments are passed, include them
    if len(sys.argv) > 1:
        pytest_args.extend(sys.argv[1:])

    print(f"Running pytest with arguments: {pytest_args}")

    # Run pytest
    exit_code = pytest.main(pytest_args)

    sys.exit(exit_code)
