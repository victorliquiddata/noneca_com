# Product extraction
# src/extractors/items_extractor.py
import logging
from src.extractors.ml_api_client import create_client

logger = logging.getLogger(__name__)


def extract_items(seller_id, limit=50):
    client, token = create_client()
    try:
        items = client.get_items(token, seller_id, limit=limit)
        return items or []
    except Exception as e:
        logger.error(f"Failed to extract items for seller {seller_id}: {e}")
        return []
