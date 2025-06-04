import os
import tempfile
import pytest
from datetime import datetime, timezone

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from src.loaders.data_loader import load_items_to_db
from src.models.models import Base, Item, PriceHistory


@pytest.fixture
def temp_sqlite_db(tmp_path):
    """
    Create a temporary SQLite file on disk, yield its URL,
    and clean it up automatically.
    """
    db_file = tmp_path / "test.db"
    db_url = f"sqlite:///{db_file}"
    engine = create_engine(db_url, future=True)
    Base.metadata.create_all(engine)
    yield db_url  # tests can consume this URL


def test_insert_and_price_history_snapshot(temp_sqlite_db):
    now = datetime.now(timezone.utc)
    record = {
        "item_id": "T1",
        "title": "TestItem",
        "category_id": "C1",
        "current_price": 10.0,
        "original_price": 20.0,
        "available_quantity": 5,
        "sold_quantity": 1,
        "condition": "new",
        "brand": "BrandX",
        "size": "L",
        "color": "Red",
        "gender": "unisex",
        "views": 100,
        "conversion_rate": 0.01,
        "seller_id": 123,
        "updated_at": now,
        "discount_percentage": 50.0,
    }

    # Use the same file-based URL for loader and test session
    load_items_to_db([record], db_url=temp_sqlite_db)

    engine = create_engine(temp_sqlite_db, future=True)
    session = Session(engine)
    itm = session.scalars(select(Item).where(Item.item_id == "T1")).one_or_none()
    assert itm is not None
    assert itm.current_price == pytest.approx(10.0)

    hist = session.scalars(
        select(PriceHistory).where(PriceHistory.item_id == "T1")
    ).all()
    assert len(hist) == 1
    assert hist[0].price == pytest.approx(10.0)
    session.close()


def test_upsert_and_history_append(temp_sqlite_db):
    now = datetime.now(timezone.utc)
    r1 = {
        "item_id": "T2",
        "title": "UpsertItem",
        "category_id": "C2",
        "current_price": 5.0,
        "original_price": 5.0,
        "available_quantity": 10,
        "sold_quantity": 0,
        "condition": "new",
        "brand": None,
        "size": None,
        "color": None,
        "gender": None,
        "views": 0,
        "conversion_rate": 0.0,
        "seller_id": 456,
        "updated_at": now,
        "discount_percentage": 0.0,
    }

    load_items_to_db([r1], db_url=temp_sqlite_db)
    engine = create_engine(temp_sqlite_db, future=True)
    session = Session(engine)
    first = session.scalars(select(Item).where(Item.item_id == "T2")).one()
    assert first.current_price == pytest.approx(5.0)
    h1 = session.scalars(select(PriceHistory).where(PriceHistory.item_id == "T2")).all()
    assert len(h1) == 1
    session.close()

    later = datetime.now(timezone.utc)
    r2 = {**r1, "current_price": 8.0, "sold_quantity": 2, "updated_at": later}
    load_items_to_db([r2], db_url=temp_sqlite_db)

    session = Session(engine)
    updated = session.scalars(select(Item).where(Item.item_id == "T2")).one()
    assert updated.current_price == pytest.approx(8.0)
    h2 = session.scalars(select(PriceHistory).where(PriceHistory.item_id == "T2")).all()
    assert len(h2) == 2
    session.close()
