```python
# ---
# API client
# src/extractors/ml_api_client.py
#!/usr/bin/env python3
import os
import json
import requests
import secrets
from datetime import datetime, timedelta
from config.config import cfg


class MLClient:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update(
            {"Accept": "application/json", "User-Agent": "MLExtractor/1.0"}
        )
        self._rate = {"calls": 0, "reset": datetime.now()}

    def _check_rate(self):
        now = datetime.now()
        if now - self._rate["reset"] > timedelta(minutes=1):
            self._rate = {"calls": 0, "reset": now}
        if self._rate["calls"] >= cfg.rate_limit:
            raise Exception("Rate limit exceeded")
        self._rate["calls"] += 1

    def _req(self, method, endpoint, **kwargs):
        self._check_rate()
        url = f"{cfg.api_url}{endpoint}"

        kwargs.setdefault("headers", {}).update(
            {"X-Request-ID": secrets.token_hex(8), "Cache-Control": "no-cache"}
        )

        try:
            resp = self.session.request(method, url, timeout=cfg.timeout, **kwargs)
            resp.raise_for_status()
            return {} if resp.status_code == 204 else resp.json()
        except requests.exceptions.HTTPError:
            status = resp.status_code
            try:
                err = resp.json()
            except ValueError:
                err = {"error": "Invalid JSON"}

            error_map = {
                401: f"Unauthorized: {err}",
                403: f"Forbidden: {err}",
                404: f"Not found: {endpoint}",
                429: "Rate limited",
            }
            raise Exception(error_map.get(status, f"HTTP {status}: {err}"))
        except requests.exceptions.Timeout:
            raise Exception("Request timeout")
        except Exception as e:
            raise Exception(f"Request failed: {str(e)}")

    def _auth(self, token):
        self.session.headers.update({"Authorization": f"Bearer {token}"})

    # Core API methods
    def get_user(self, token, user_id="me", attrs=None):
        self._auth(token)
        params = {"attributes": attrs} if attrs else {}
        return self._req("GET", f"/users/{user_id}", params=params)

    def get_items(self, token, seller_id, limit=50, status="active"):
        self._auth(token)
        params = {"limit": limit, "status": status}
        result = self._req("GET", f"/users/{seller_id}/items/search", params=params)
        return [self.get_item(token, item_id) for item_id in result.get("results", [])]

    def get_item(self, token, item_id, attrs=None):
        self._auth(token)
        params = {"attributes": attrs} if attrs else {}
        return self._req("GET", f"/items/{item_id}", params=params)

    def get_desc(self, token, item_id):
        self._auth(token)
        try:
            return self._req("GET", f"/items/{item_id}/description")
        except Exception as e:
            return {"plain_text": "N/A", "error": str(e)}

    def get_reviews(self, token, item_id):
        self._auth(token)
        try:
            return self._req("GET", f"/reviews/item/{item_id}")
        except Exception as e:
            return {
                "rating_average": 0,
                "total_reviews": 0,
                "reviews": [],
                "error": str(e),
            }

    def get_questions(self, token, item_id, limit=10):
        self._auth(token)
        try:
            params = {"item_id": item_id, "limit": limit}
            return self._req("GET", "/questions/search", params=params)
        except Exception as e:
            return {"questions": [], "total": 0, "error": str(e)}

    def get_orders(self, token, seller_id, limit=50):
        self._auth(token)
        params = {"seller": seller_id, "limit": limit}
        return self._req("GET", "/orders/search", params=params)["results"]

    def get_listing_types(self, token, site_id):
        self._auth(token)
        return self._req("GET", f"/sites/{site_id}/listing_types")

    def get_listing_exposures(self, token, site_id):
        self._auth(token)
        return self._req("GET", f"/sites/{site_id}/listing_exposures")

    def search(
        self,
        token,
        site_id,
        query=None,
        seller_id=None,
        category=None,
        limit=50,
        offset=0,
    ):
        # Authenticate immediately
        self._auth(token)

        # Always build the same param dictionary
        params = {"limit": limit, "offset": offset}
        if query:
            params["q"] = query
        if seller_id:
            params["seller_id"] = seller_id
        if category:
            params["category"] = category

        # 1) Try the generic /sites/{site_id}/search
        try:
            return self._req("GET", f"/sites/{site_id}/search", params=params)
        except Exception as e:
            # If it fails with 403 or 401, fall back to “items by seller” if we can
            msg = str(e).lower()
            if "403" in msg or "401" in msg:
                # If caller already passed seller_id, just re‐raise (nothing else to try)
                if seller_id:
                    raise

                # Otherwise, fetch the user’s own ID and do /users/{id}/items/search
                user = self.get_user(token)  # returns JSON with “id” field
                fallback_seller = user["id"]
                return self.get_items(token, fallback_seller, limit=limit)
            # For any other exception, re‐raise
            raise

    def get_categories(self, token, site_id):
        try:
            return self._req("GET", f"/sites/{site_id}/categories")
        except Exception:
            return self._req("GET", f"/sites/{site_id}/categories")

    def get_category(self, token, category_id):
        try:
            return self._req("GET", f"/categories/{category_id}")
        except Exception:
            return self._req("GET", f"/categories/{category_id}")

    def get_trends(self, token, site_id, category_id=None):
        endpoint = f"/trends/{site_id}"
        if category_id:
            endpoint += f"/{category_id}"
        return self._req("GET", endpoint, headers={"Authorization": f"Bearer {token}"})

    def validate_item(self, token, item_data):
        self._auth(token)
        try:
            resp = self.session.post(
                f"{cfg.api_url}/items/validate",
                json=item_data,
                headers=self.session.headers,
                timeout=cfg.timeout,
            )
            return {
                "valid": resp.status_code == 204,
                "errors": resp.json() if resp.status_code != 204 else None,
            }
        except Exception as e:
            return {"valid": False, "errors": str(e)}


# Token management
def save_tokens(tokens):
    tokens["expires_at"] = (
        datetime.now() + timedelta(seconds=tokens["expires_in"])
    ).isoformat()
    with open(cfg.token_file, "w") as f:
        json.dump(tokens, f)


def load_tokens():
    if os.path.exists(cfg.token_file):
        with open(cfg.token_file) as f:
            return json.load(f)
    return {
        "access_token": cfg.fallback_access,
        "token_type": "Bearer",
        "expires_in": 21600,
        "refresh_token": cfg.fallback_refresh,
        "expires_at": cfg.fallback_expires,
    }


def is_valid(tokens):
    if not tokens:
        return False
    expires_at = datetime.fromisoformat(tokens["expires_at"])
    return datetime.now() < expires_at - timedelta(minutes=5)


def refresh_token(refresh_token):
    resp = requests.post(
        f"{cfg.api_url}/oauth/token",
        data={
            "grant_type": "refresh_token",
            "client_id": cfg.client_id,
            "client_secret": cfg.client_secret,
            "refresh_token": refresh_token,
        },
        timeout=cfg.timeout,
    )
    resp.raise_for_status()
    return resp.json()


def get_token():
    tokens = load_tokens()

    if tokens and is_valid(tokens):
        return tokens["access_token"]

    if tokens and "refresh_token" in tokens:
        try:
            new_tokens = refresh_token(tokens["refresh_token"])
            save_tokens(new_tokens)
            return new_tokens["access_token"]
        except Exception:
            pass

    return load_tokens()["access_token"]


def create_client():
    return MLClient(), get_token()

# ---

# src/extractors/items_extractor.py
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

            try:
                # Add description if requested
                if include_descriptions:
                    description = client.get_desc(token, item_id)
                    enriched_item["description"] = description.get("plain_text", "N/A")

                # Add reviews if requested
                if include_reviews:
                    reviews = client.get_reviews(token, item_id)
                    enriched_item["rating_average"] = reviews.get("rating_average", 0)
                    enriched_item["total_reviews"] = reviews.get("total_reviews", 0)

            except Exception as e:
                logger.warning(f"Failed to enrich item {item_id}: {e}")

            enriched_items.append(enriched_item)

        logger.info(
            f"Successfully enriched {len(enriched_items)} items for seller {seller_id}"
        )
        return enriched_items

    except Exception as e:
        logger.error(f"Failed to extract enriched items for seller {seller_id}: {e}")
        return []

# ---

# Data loading
# src/loaders/data_loader.py

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.exc import SQLAlchemyError

from src.models.models import Item, PriceHistory, Seller, create_all_tables


def load_items_to_db(enriched_items, db_url="sqlite:///./noneca_analytics.db"):
    """
    Upsert a list of enriched item dicts into `items` and append to `price_history`.
    If seller info is embedded, upsert into `sellers` as well.
    """
    if not enriched_items:
        return

    engine = create_engine(db_url, echo=False, future=True)
    Session = sessionmaker(bind=engine)
    create_all_tables(engine)

    session = Session()
    try:
        for record in enriched_items:
            item_id = record.get("item_id")
            if not item_id:
                continue  # skip invalid entries

            # Upsert item
            existing = session.get(Item, item_id)
            if existing:
                # Update only the mutable fields
                for field in (
                    "title",
                    "category_id",
                    "current_price",
                    "original_price",
                    "available_quantity",
                    "sold_quantity",
                    "condition",
                    "brand",
                    "size",
                    "color",
                    "gender",
                    "views",
                    "conversion_rate",
                    "seller_id",
                    "updated_at",
                ):
                    if field in record:
                        setattr(existing, field, record[field])
                session.add(existing)
            else:
                item_kwargs = {k: record[k] for k in record.keys() if hasattr(Item, k)}
                session.add(Item(**item_kwargs))

            # Optionally upsert seller if detailed info present
            seller_info = {
                "seller_id": record.get("seller_id"),
                "nickname": record.get("seller_nickname"),
                "reputation_score": record.get("seller_reputation"),
                "transactions_completed": record.get("seller_transactions"),
                "is_competitor": record.get("is_competitor"),
                "market_share_pct": record.get("market_share_pct"),
            }
            sid = seller_info.get("seller_id")
            if sid and any(v is not None for v in seller_info.values()):
                existing_seller = session.get(Seller, sid)
                if existing_seller:
                    for key, val in seller_info.items():
                        if key != "seller_id" and val is not None:
                            setattr(existing_seller, key, val)
                    session.add(existing_seller)
                else:
                    session.add(Seller(**seller_info))

            # Append price history snapshot
            price_record = {
                "item_id": item_id,
                "price": record.get("current_price"),
                "discount_percentage": record.get("discount_percentage"),
                "competitor_rank": record.get("competitor_rank"),
                "price_position": record.get("price_position"),
            }
            session.add(PriceHistory(**price_record))

        session.commit()
    except SQLAlchemyError:
        session.rollback()
        raise
    finally:
        session.close()

# ---

from sqlalchemy import (
    Column,
    String,
    Integer,
    Float,
    Boolean,
    Date,
    DateTime,
    func,
    text,
)
from sqlalchemy.orm import declarative_base

Base = declarative_base()


class Item(Base):
    __tablename__ = "items"

    item_id = Column(String(50), primary_key=True)
    title = Column(String(500))
    category_id = Column(String(50))
    current_price = Column(Float(precision=2))
    original_price = Column(Float(precision=2))
    available_quantity = Column(Integer)
    sold_quantity = Column(Integer)
    condition = Column(String(20))
    brand = Column(String(100))
    size = Column(String(20))
    color = Column(String(50))
    gender = Column(String(20))
    views = Column(Integer, default=0)
    conversion_rate = Column(Float(precision=4))
    seller_id = Column(Integer)
    created_at = Column(DateTime, server_default=text("CURRENT_TIMESTAMP"))
    updated_at = Column(
        DateTime,
        default=func.current_timestamp(),  # pylint: disable=E1102
        onupdate=func.current_timestamp(),  # pylint: disable=E1102
    )


class PriceHistory(Base):
    __tablename__ = "price_history"

    id = Column(Integer, primary_key=True, autoincrement=True)
    item_id = Column(String(50))
    price = Column(Float(precision=2))
    discount_percentage = Column(Float(precision=2))
    competitor_rank = Column(Integer, nullable=True)
    price_position = Column(String(20), nullable=True)
    recorded_at = Column(DateTime, server_default=text("CURRENT_TIMESTAMP"))


class Seller(Base):
    __tablename__ = "sellers"

    seller_id = Column(Integer, primary_key=True)
    nickname = Column(String(100), nullable=True)
    reputation_score = Column(Float(precision=2), nullable=True)
    transactions_completed = Column(Integer, nullable=True)
    is_competitor = Column(Boolean, default=False)
    market_share_pct = Column(Float(precision=2), nullable=True)


class MarketTrend(Base):
    __tablename__ = "market_trends"

    id = Column(Integer, primary_key=True, autoincrement=True)
    keyword = Column(String(200))
    search_volume = Column(Integer)
    category_id = Column(String(50))
    trend_date = Column(Date)
    growth_rate = Column(Float(precision=2))


def create_all_tables(engine):
    """Create all tables in the target database."""
    Base.metadata.create_all(engine)

# ---

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

# ---

# Configuration management
## config/config.py
#!/usr/bin/env python3
import os
from dataclasses import dataclass
from dotenv import load_dotenv

load_dotenv()


@dataclass
class Config:
    client_id: str = os.getenv("ML_CLIENT_ID")
    client_secret: str = os.getenv("ML_CLIENT_SECRET")
    redirect_uri: str = os.getenv("ML_REDIRECT_URI")
    timeout: int = int(os.getenv("API_TIMEOUT", 30))
    rate_limit: int = int(os.getenv("RATE_LIMIT", 100))

    # API URLs
    api_url: str = "https://api.mercadolibre.com"
    auth_url: str = "https://auth.mercadolivre.com.br"

    # Files
    token_file: str = "ml_tokens.json"

    # Fallback tokens
    fallback_access: str = os.getenv("ACCESS_TOKEN")
    fallback_refresh: str = os.getenv("REFRESH_TOKEN")
    fallback_expires: str = os.getenv("TOKEN_EXPIRES")


cfg = Config()

# ---

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
        "354140329",  # Example seller ID - replace with actual sellers
        # "987654321",  # Example seller ID - replace with actual sellers
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

# ---
```