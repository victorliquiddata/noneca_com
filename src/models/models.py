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
