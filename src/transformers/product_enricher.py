# src/transformers/product_enricher.py
from datetime import datetime, timezone
from typing import List, Dict, Optional, Any


def _get_attr(attrs: Optional[List[Dict]], key: str) -> Optional[str]:
    """Extract attribute value by key from attributes list."""
    if not attrs:
        return None

    for attr in attrs:
        if attr.get("id") == key:
            value = attr.get("value_name") or attr.get("value_id")
            # Return None if value is empty string or None
            return value if value else None
    return None


def _safe_divide(numerator: float, denominator: float, precision: int = 4) -> float:
    """Safely divide two numbers, returning 0.0 if denominator is 0."""
    if not denominator:
        return 0.0
    return round(numerator / denominator, precision)


def _calculate_discount_percentage(original: float, current: float) -> float:
    """Calculate discount percentage between original and current price."""
    if not original or original <= current:
        return 0.0
    return round((original - current) / original * 100, 2)


def enrich_item(item: Dict[str, Any]) -> Dict[str, Any]:
    """
    Enrich a single item with computed fields and standardized format.

    Args:
        item: Raw item dictionary from API

    Returns:
        Enriched item dictionary
    """
    if not item:
        return {}

    attrs = item.get("attributes", [])

    # Extract attributes - note the correct attribute key for color
    brand = _get_attr(attrs, "BRAND")
    size = _get_attr(attrs, "SIZE")
    color = _get_attr(attrs, "MAIN_COLOR")  # Fixed: was "COLOR", should be "MAIN_COLOR"
    gender = _get_attr(attrs, "GENDER")

    # Calculate metrics
    views = item.get("views", 0) or 0
    sold = item.get("sold_quantity", 0) or 0
    conversion = _safe_divide(sold, views)

    current_price = float(item.get("price", 0) or 0)
    original_price = float(item.get("original_price") or current_price)
    discount_pct = _calculate_discount_percentage(original_price, current_price)

    timestamp = datetime.now(timezone.utc)

    return {
        "item_id": item.get("id"),
        "title": item.get("title"),
        "category_id": item.get("category_id"),
        "current_price": current_price,
        "original_price": original_price,
        "available_quantity": item.get("available_quantity"),
        "sold_quantity": sold,
        "condition": item.get("condition"),
        "brand": brand,
        "size": size,
        "color": color,
        "gender": gender,
        "views": views,
        "conversion_rate": conversion,
        "seller_id": item.get("seller_id"),
        "created_at": timestamp,
        "updated_at": timestamp,
        "discount_percentage": discount_pct,
    }


def enrich_items(raw_items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Enrich a list of items with computed fields and standardized format.

    Args:
        raw_items: List of raw item dictionaries from API

    Returns:
        List of enriched item dictionaries
    """
    if not raw_items:
        return []

    return [enrich_item(item) for item in raw_items if item]
