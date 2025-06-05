# Main entry point
#!/usr/bin/env python3
"""
Main ETL pipeline orchestrator for Noneca.com Mercado Livre Analytics Platform.
Extracts product data, enriches it, and loads into database.
"""

import sys
import logging
from typing import List, Dict, Optional

from src.extractors.items_extractor import extract_items_with_enrichments
from src.transformers.product_enricher import enrich_items
from src.loaders.data_loader import load_items_to_db

# Configure minimal logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler()],
)
logger = logging.getLogger(__name__)


def run_etl_pipeline(
    seller_id: str,
    limit: int = 50,
    include_descriptions: bool = True,
    include_reviews: bool = False,
    db_url: str = "sqlite:///./noneca_analytics.db",
) -> bool:
    """
    Execute complete ETL pipeline for a single seller.

    Returns:
        True if pipeline completed successfully, False otherwise
    """
    logger.info(f"Starting ETL pipeline for seller {seller_id}")

    # Extract
    logger.info("Extracting items...")
    raw_items = extract_items_with_enrichments(
        seller_id=seller_id,
        limit=limit,
        include_descriptions=include_descriptions,
        include_reviews=include_reviews,
    )

    if not raw_items:
        logger.warning(f"No items extracted for seller {seller_id}")
        return False

    logger.info(f"Extracted {len(raw_items)} items")

    # Transform
    logger.info("Enriching items...")
    enriched_items = enrich_items(raw_items)

    if not enriched_items:
        logger.error("Enrichment failed - no items to load")
        return False

    logger.info(f"Enriched {len(enriched_items)} items")

    # Load
    logger.info("Loading items to database...")
    try:
        load_items_to_db(enriched_items, db_url)
        logger.info("ETL pipeline completed successfully")
        return True
    except Exception as e:
        logger.error(f"Loading failed: {e}")
        return False


def run_multi_seller_pipeline(
    seller_ids: List[str],
    limit: int = 50,
    db_url: str = "sqlite:///./noneca_analytics.db",
) -> Dict[str, bool]:
    """
    Execute ETL pipeline for multiple sellers.

    Returns:
        Dictionary mapping seller_id to success status
    """
    results = {}

    for seller_id in seller_ids:
        try:
            success = run_etl_pipeline(seller_id=seller_id, limit=limit, db_url=db_url)
            results[seller_id] = success
        except Exception as e:
            logger.error(f"Pipeline failed for seller {seller_id}: {e}")
            results[seller_id] = False

    return results


def main():
    """Main entry point - run ETL pipeline with default configuration."""

    # Default seller IDs for intimate apparel market analysis
    # These would typically come from config or command line args
    default_sellers = [
        "123456789",  # Example seller ID - replace with actual sellers
        "987654321",  # Example seller ID - replace with actual sellers
    ]

    # Check for command line seller ID argument
    seller_id = sys.argv[1] if len(sys.argv) > 1 else None

    if seller_id:
        # Single seller mode
        logger.info(f"Running ETL for single seller: {seller_id}")
        success = run_etl_pipeline(seller_id, limit=100)
        sys.exit(0 if success else 1)

    # Multi-seller mode
    logger.info("Running ETL for multiple sellers")
    results = run_multi_seller_pipeline(default_sellers, limit=50)

    # Report results
    successful = sum(results.values())
    total = len(results)
    logger.info(
        f"Pipeline completed: {successful}/{total} sellers processed successfully"
    )

    # Exit with error code if any pipeline failed
    sys.exit(0 if successful == total else 1)


if __name__ == "__main__":
    main()
