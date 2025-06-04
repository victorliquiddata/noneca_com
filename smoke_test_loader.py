# scripts/smoke_test_loader.py

from datetime import datetime
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

# Ensure PYTHONPATH includes the project root when running this script
from src.loaders.data_loader import load_items_to_db
from src.models.models import Item, PriceHistory, Seller


def build_dummy_items(first_run=True):
    now = datetime.utcnow()
    base = {
        "item_id": "DUMMY123",
        "title": "Smoke Test Product",
        "category_id": "TESTCAT",
        "current_price": 20.0 if first_run else 25.0,
        "original_price": 40.0,
        "available_quantity": 5,
        "sold_quantity": 1 if first_run else 2,
        "condition": "new",
        "brand": "SmokeBrand",
        "size": "M",
        "color": "Green",
        "gender": "unisex",
        "views": 100,
        "conversion_rate": 0.01,
        "seller_id": 9999,
        "updated_at": now,
        "discount_percentage": 50.0 if first_run else 37.5,
        # Optional seller info:
        "seller_nickname": "SmokeSeller",
        "seller_reputation": 4.9,
        "seller_transactions": 200,
        "is_competitor": False,
        "market_share_pct": 1.2,
        # Optional price-history extras:
        "competitor_rank": 2,
        "price_position": "low",
    }
    return [base]


def main():
    db_url = "sqlite:///./noneca_analytics.db"

    # 1) First insert
    print("=== First load ===")
    enriched = build_dummy_items(first_run=True)
    load_items_to_db(enriched, db_url=db_url)

    engine = create_engine(db_url, future=True)
    session = Session(engine)

    item_row = session.scalars(
        select(Item).where(Item.item_id == "DUMMY123")
    ).one_or_none()
    print("Item after first load:", item_row)

    history_rows = session.scalars(
        select(PriceHistory).where(PriceHistory.item_id == "DUMMY123")
    ).all()
    print("PriceHistory count after first load:", len(history_rows))

    seller_row = session.scalars(
        select(Seller).where(Seller.seller_id == 9999)
    ).one_or_none()
    print("Seller after first load:", seller_row)

    session.close()

    # 2) Second run (simulate price change)
    print("\n=== Second load (price change) ===")
    enriched2 = build_dummy_items(first_run=False)
    load_items_to_db(enriched2, db_url=db_url)

    session = Session(engine)
    updated_item = session.scalars(
        select(Item).where(Item.item_id == "DUMMY123")
    ).one_or_none()
    print("Item after second load:", updated_item)

    history_rows2 = session.scalars(
        select(PriceHistory).where(PriceHistory.item_id == "DUMMY123")
    ).all()
    print("PriceHistory count after second load:", len(history_rows2))

    session.close()


if __name__ == "__main__":
    main()
