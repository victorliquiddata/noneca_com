# Product enrichment
# transformers/product_enricher.py
from datetime import datetime


def _get_attr(attrs, key):
    for a in attrs or []:
        if a.get("id") == key:
            return a.get("value_name") or a.get("value_id")
    return None


def enrich_items(raw_items):
    enriched = []
    for item in raw_items:
        attrs = item.get("attributes", [])
        brand = _get_attr(attrs, "BRAND")
        size = _get_attr(attrs, "SIZE")
        color = _get_attr(attrs, "COLOR")
        gender = _get_attr(attrs, "GENDER")

        views = item.get("views", 0) or 0
        sold = item.get("sold_quantity", 0) or 0
        conversion = round(sold / views, 4) if views else 0.0

        current_price = item.get("price") or 0.0
        original_price = item.get("original_price") or current_price
        discount_pct = (
            round((original_price - current_price) / original_price * 100, 2)
            if original_price
            else 0.0
        )

        enriched.append(
            {
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
                "created_at": datetime.utcnow(),
                "updated_at": datetime.utcnow(),
                "discount_percentage": discount_pct,
            }
        )
    return enriched
