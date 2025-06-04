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
