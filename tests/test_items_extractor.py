# src/extractors/items_extractor.py
import pytest
import sys
import os
import logging
from typing import List, Dict, Optional
from src.extractors.ml_api_client import create_client

logger = logging.getLogger(__name__)


def extract_items(seller_id: str, limit: int = 50) -> List[Dict]:
    """
    Extract items for a given seller using the ML API client.

    Args:
        seller_id: The seller ID to extract items for
        limit: Maximum number of items to extract (default: 50)

    Returns:
        List of item dictionaries, or empty list if extraction fails
    """
    if not seller_id:
        logger.error("Seller ID is required")
        return []

    if limit <= 0:
        logger.error("Limit must be positive")
        return []

    try:
        client, token = create_client()
        items = client.get_items(token, seller_id, limit=limit)

        if not items:
            logger.info(f"No items found for seller {seller_id}")
            return []

        logger.info(f"Successfully extracted {len(items)} items for seller {seller_id}")
        return items

    except Exception as e:
        logger.error(f"Failed to extract items for seller {seller_id}: {e}")
        return []


def extract_item_details(item_id: str, token: Optional[str] = None) -> Optional[Dict]:
    """
    Extract detailed information for a single item.

    Args:
        item_id: The item ID to extract details for
        token: Authentication token. If None, will create new client.

    Returns:
        Item details dictionary, or None if extraction fails
    """
    if not item_id:
        logger.error("Item ID is required")
        return None

    try:
        if token is None:
            client, token = create_client()
        else:
            client = create_client()[0]

        item_details = client.get_item(token, item_id)

        if item_details:
            logger.info(f"Successfully extracted details for item {item_id}")
            return item_details
        else:
            logger.warning(f"No details found for item {item_id}")
            return None

    except Exception as e:
        logger.error(f"Failed to extract details for item {item_id}: {e}")
        return None


def extract_items_with_enrichments(
    seller_id: str,
    limit: int = 50,
    include_descriptions: bool = True,
    include_reviews: bool = False,
) -> List[Dict]:
    """
    Extract items with additional details like descriptions and optionally reviews.

    Args:
        seller_id: The seller ID to extract items for
        limit: Maximum number of items to extract
        include_descriptions: Whether to include item descriptions
        include_reviews: Whether to include review data

    Returns:
        List of enriched item dictionaries
    """
    if not seller_id:
        logger.error("Seller ID is required")
        return []

    try:
        client, token = create_client()
        items = extract_items(seller_id, limit)

        if not items:
            return []

        enriched_items = []
        for item in items:
            item_id = item.get("id")
            if not item_id:
                enriched_items.append(item)
                continue

            enriched_item = item.copy()

            # Add description if requested
            if include_descriptions:
                try:
                    description = client.get_desc(token, item_id)
                    enriched_item["description"] = description.get("plain_text", "N/A")
                except Exception as e:
                    logger.warning(f"Failed to get description for item {item_id}: {e}")

            # Add reviews if requested
            if include_reviews:
                try:
                    reviews = client.get_reviews(token, item_id)
                    enriched_item["rating_average"] = reviews.get("rating_average", 0)
                    enriched_item["total_reviews"] = reviews.get("total_reviews", 0)
                except Exception as e:
                    logger.warning(f"Failed to get reviews for item {item_id}: {e}")

            enriched_items.append(enriched_item)

        logger.info(
            f"Successfully enriched {len(enriched_items)} items for seller {seller_id}"
        )
        return enriched_items

    except Exception as e:
        logger.error(f"Failed to extract enriched items for seller {seller_id}: {e}")
        return []


# run_tests.py


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
