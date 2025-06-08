#!/usr/bin/env python3
# seller_orders_pipeline.py
"""
Complete ETL Pipeline for MercadoLibre Seller Orders
Extracts full order history, transforms data, and loads into SQLite database.
TO RUN USE -------> python seller_orders_pipeline.py --seller 354140329
"""
import argparse
import json
import os
import sys
import time
import logging
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import List, Dict, Any, Optional, Generator
import sqlite3
from sqlalchemy import func

# Third-party imports
try:
    import requests
    from sqlalchemy import (
        create_engine,
        Column,
        Integer,
        String,
        DateTime,
        Numeric,
        Text,
        ForeignKey,
        Boolean,
        JSON,
    )
    from sqlalchemy.orm import sessionmaker, relationship, declarative_base
    from sqlalchemy.exc import SQLAlchemyError
    from tqdm import tqdm
    from dotenv import load_dotenv
except ImportError as e:
    print(f"Missing required dependency: {e}")
    print("Install with: pip install requests sqlalchemy tqdm python-dotenv")
    sys.exit(1)

# Ensure project root for imports
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, PROJECT_ROOT)

try:
    from src.extractors.ml_api_client import create_client
except ImportError:
    print(
        "Could not import ml_api_client. Ensure src/extractors/ml_api_client.py exists."
    )
    sys.exit(1)

# Load environment variables
load_dotenv()

# SQLAlchemy setup
Base = declarative_base()


class Order(Base):
    __tablename__ = "orders"

    id = Column(String, primary_key=True)
    seller_id = Column(Integer, nullable=False)
    buyer_id = Column(Integer, nullable=True)
    buyer_nickname = Column(String, nullable=True)
    status = Column(String, nullable=False)
    status_detail = Column(String, nullable=True)
    date_created = Column(DateTime, nullable=False)
    date_closed = Column(DateTime, nullable=True)
    date_last_updated = Column(DateTime, nullable=True)
    expiration_date = Column(DateTime, nullable=True)
    total_amount = Column(Numeric(10, 2), nullable=False)
    paid_amount = Column(Numeric(10, 2), nullable=False)
    currency_id = Column(String, nullable=False)
    shipping_cost = Column(Numeric(10, 2), nullable=True)
    pack_id = Column(String, nullable=True)
    fulfilled = Column(Boolean, nullable=True)
    comment = Column(Text, nullable=True)
    tags = Column(JSON, nullable=True)
    feedback_data = Column(JSON, nullable=True)
    context_data = Column(JSON, nullable=True)
    processing_time_hours = Column(Numeric(10, 2), nullable=True)

    # Relationships
    items = relationship("OrderItem", back_populates="order")
    payments = relationship("Payment", back_populates="order")


class OrderItem(Base):
    __tablename__ = "order_items"

    id = Column(Integer, primary_key=True, autoincrement=True)
    order_id = Column(String, ForeignKey("orders.id"), nullable=False)
    element_id = Column(Integer, nullable=True)
    item_id = Column(String, nullable=False)
    title = Column(String, nullable=False)
    category_id = Column(String, nullable=True)
    variation_id = Column(String, nullable=True)
    seller_sku = Column(String, nullable=True)
    quantity = Column(Integer, nullable=False)
    unit_price = Column(Numeric(10, 2), nullable=False)
    full_unit_price = Column(Numeric(10, 2), nullable=True)
    sale_fee = Column(Numeric(10, 2), nullable=True)
    listing_type_id = Column(String, nullable=True)
    condition = Column(String, nullable=True)
    warranty = Column(String, nullable=True)
    variation_attributes = Column(JSON, nullable=True)

    # Relationship
    order = relationship("Order", back_populates="items")


class Payment(Base):
    __tablename__ = "payments"

    id = Column(String, primary_key=True)
    order_id = Column(String, ForeignKey("orders.id"), nullable=False)
    payer_id = Column(Integer, nullable=True)
    collector_id = Column(Integer, nullable=False)
    status = Column(String, nullable=False)
    status_detail = Column(String, nullable=True)
    payment_method_id = Column(String, nullable=False)
    payment_type = Column(String, nullable=False)
    operation_type = Column(String, nullable=False)
    transaction_amount = Column(Numeric(10, 2), nullable=False)
    total_paid_amount = Column(Numeric(10, 2), nullable=False)
    transaction_amount_refunded = Column(Numeric(10, 2), nullable=True)
    date_created = Column(DateTime, nullable=False)
    date_approved = Column(DateTime, nullable=True)
    date_last_modified = Column(DateTime, nullable=True)
    installments = Column(Integer, nullable=True)
    installment_amount = Column(Numeric(10, 2), nullable=True)
    issuer_id = Column(String, nullable=True)
    reason = Column(String, nullable=True)
    shipping_cost = Column(Numeric(10, 2), nullable=True)
    taxes_amount = Column(Numeric(10, 2), nullable=True)
    coupon_amount = Column(Numeric(10, 2), nullable=True)

    # Relationship
    order = relationship("Order", back_populates="payments")


class ETLState(Base):
    __tablename__ = "etl_state"

    id = Column(Integer, primary_key=True)
    seller_id = Column(Integer, nullable=False)
    last_processed_date = Column(DateTime, nullable=True)
    last_offset = Column(Integer, nullable=False, default=0)
    total_processed = Column(Integer, nullable=False, default=0)
    last_run_date = Column(DateTime, nullable=False)
    status = Column(String, nullable=False, default="running")
    last_order_id = Column(String, nullable=True)  # Track last processed order


class MercadoLibreETL:
    def __init__(self, db_path: str, batch_size: int = 100):
        self.db_path = db_path
        self.batch_size = batch_size
        self.engine = create_engine(f"sqlite:///{db_path}")
        Base.metadata.create_all(self.engine)
        Session = sessionmaker(bind=self.engine)
        self.session = Session()
        self.client = None
        self.token = None
        self.logger = self._setup_logging()

    def _setup_logging(self) -> logging.Logger:
        """Setup logging configuration"""
        logger = logging.getLogger("ml_etl")
        logger.setLevel(logging.INFO)

        if not logger.handlers:
            handler = logging.StreamHandler()
            formatter = logging.Formatter(
                "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
            )
            handler.setFormatter(formatter)
            logger.addHandler(handler)

        return logger

    def initialize_client(self):
        """Initialize MercadoLibre API client"""
        try:
            self.client, self.token = create_client()
            self.logger.info("MercadoLibre API client initialized successfully")
        except Exception as e:
            self.logger.error(f"Failed to initialize ML client: {e}")
            raise

    def safe_api_call(self, func, *args, **kwargs):
        """Make API call with retry logic"""
        max_retries = 3
        retry_delay = 1

        for attempt in range(max_retries):
            try:
                return func(*args, **kwargs)
            except requests.exceptions.HTTPError as e:
                if e.response.status_code == 429:  # Rate limit
                    wait_time = min(
                        60 * (2**attempt), 300
                    )  # Exponential backoff, max 5 min
                    self.logger.warning(f"Rate limit hit, waiting {wait_time}s...")
                    time.sleep(wait_time)
                    continue
                elif e.response.status_code >= 500:  # Server errors
                    if attempt < max_retries - 1:
                        self.logger.warning(
                            f"Server error {e.response.status_code}, retrying..."
                        )
                        time.sleep(retry_delay * (2**attempt))
                        continue
                raise
            except requests.exceptions.RequestException as e:
                if attempt < max_retries - 1:
                    self.logger.warning(f"Request failed, retrying: {e}")
                    time.sleep(retry_delay * (2**attempt))
                    continue
                raise

        raise Exception(f"Failed after {max_retries} retries")

    def fetch_orders_page(
        self,
        seller_id: int,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
    ) -> List[Dict[Any, Any]]:
        """Fetch orders using the available API client parameters"""

        def _get_orders():
            # Use only the parameters that your API client actually supports
            # Check your ml_api_client.py file to see what parameters get_orders accepts
            return self.client.get_orders(
                self.token,
                seller_id=seller_id,
                limit=self.batch_size,
                # Removed offset parameter as it's not supported
            )

        return self.safe_api_call(_get_orders)

    def fetch_all_orders(
        self,
        seller_id: int,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
    ) -> Generator[List[Dict], None, None]:
        """Generator that yields pages of orders - modified to work without offset"""
        total_fetched = 0
        seen_order_ids = set()

        # Load existing state if available
        state = self.session.query(ETLState).filter_by(seller_id=seller_id).first()
        if state and state.status == "paused":
            total_fetched = state.total_processed
            self.logger.info(f"Resuming, total processed: {total_fetched}")

            # Load previously seen order IDs to avoid reprocessing
            existing_orders = (
                self.session.query(Order.id).filter_by(seller_id=seller_id).all()
            )
            seen_order_ids = {order.id for order in existing_orders}

        consecutive_empty_calls = 0
        max_empty_calls = 3  # Stop after 3 consecutive calls with no new orders

        while consecutive_empty_calls < max_empty_calls:
            try:
                orders = self.fetch_orders_page(seller_id, start_date, end_date)

                if not orders:
                    consecutive_empty_calls += 1
                    self.logger.info(
                        f"No orders returned (attempt {consecutive_empty_calls}/{max_empty_calls})"
                    )
                    continue

                # Filter out orders we've already processed
                new_orders = [
                    order for order in orders if order["id"] not in seen_order_ids
                ]

                if not new_orders:
                    consecutive_empty_calls += 1
                    self.logger.info(
                        f"No new orders in batch (attempt {consecutive_empty_calls}/{max_empty_calls})"
                    )
                    # Add current order IDs to seen set
                    for order in orders:
                        seen_order_ids.add(order["id"])
                    continue

                # Reset empty call counter since we found new orders
                consecutive_empty_calls = 0

                # Filter by date range if specified
                filtered_orders = self._filter_orders_by_date(
                    new_orders, start_date, end_date
                )

                if not filtered_orders:
                    self.logger.info("No orders in specified date range")
                    # Still add to seen set to avoid reprocessing
                    for order in new_orders:
                        seen_order_ids.add(order["id"])
                    continue

                # Add to seen set
                for order in filtered_orders:
                    seen_order_ids.add(order["id"])

                yield filtered_orders

                total_fetched += len(filtered_orders)

                # Update state
                last_order_id = filtered_orders[-1]["id"] if filtered_orders else None
                self._update_etl_state(
                    seller_id, 0, total_fetched, last_order_id=last_order_id
                )

                self.logger.info(
                    f"Fetched {len(filtered_orders)} new orders (total: {total_fetched})"
                )

                # Small delay to be respectful to the API
                time.sleep(0.5)

            except Exception as e:
                self.logger.error(f"Error fetching orders: {e}")
                # Save error state
                self._update_etl_state(seller_id, 0, total_fetched, status="error")
                raise

        self.logger.info("Finished fetching orders - no more new orders found")

    def _filter_orders_by_date(
        self, orders: List[Dict], start_date: Optional[str], end_date: Optional[str]
    ) -> List[Dict]:
        """Filter orders by date range"""
        if not start_date and not end_date:
            return orders

        filtered = []
        for order in orders:
            order_date = datetime.fromisoformat(
                order["date_created"]
                .replace("Z", "+00:00")
                .replace("-04:00", "")
                .replace("-03:00", "")
            )

            include = True
            if start_date:
                start_dt = datetime.fromisoformat(start_date)
                if order_date < start_dt:
                    include = False

            if end_date and include:
                end_dt = datetime.fromisoformat(end_date)
                if order_date > end_dt:
                    include = False

            if include:
                filtered.append(order)

        return filtered

    def _update_etl_state(
        self,
        seller_id: int,
        offset: int,
        total_processed: int,
        status: str = "running",
        last_order_id: Optional[str] = None,
    ):
        """Update ETL state in database"""
        state = self.session.query(ETLState).filter_by(seller_id=seller_id).first()
        if not state:
            state = ETLState(seller_id=seller_id)
            self.session.add(state)

        state.last_offset = offset
        state.total_processed = total_processed
        state.last_run_date = datetime.now(timezone.utc)  # Fixed deprecation warning
        state.status = status
        if last_order_id:
            state.last_order_id = last_order_id

        try:
            self.session.commit()
        except SQLAlchemyError as e:
            self.logger.error(f"Failed to update ETL state: {e}")
            self.session.rollback()

    def transform_order(self, order_data: Dict) -> Dict:
        """Transform raw order data into database format"""

        def safe_decimal(value):
            return Decimal(str(value)) if value is not None else None

        def safe_datetime(date_str):
            if not date_str:
                return None
            try:
                # Handle various date formats from ML API
                clean_date = date_str.replace("Z", "+00:00")
                if clean_date.endswith("-04:00") or clean_date.endswith("-03:00"):
                    clean_date = clean_date[:-6]
                return datetime.fromisoformat(clean_date)
            except ValueError:
                return None

        # Calculate processing time
        processing_time = None
        if order_data.get("date_created") and order_data.get("date_closed"):
            created = safe_datetime(order_data["date_created"])
            closed = safe_datetime(order_data["date_closed"])
            if created and closed:
                processing_time = (closed - created).total_seconds() / 3600  # hours

        # Transform main order
        order = {
            "id": str(order_data["id"]),
            "seller_id": order_data["seller"]["id"],
            "buyer_id": order_data.get("buyer", {}).get("id"),
            "buyer_nickname": order_data.get("buyer", {}).get("nickname"),
            "status": order_data["status"],
            "status_detail": order_data.get("status_detail"),
            "date_created": safe_datetime(order_data["date_created"]),
            "date_closed": safe_datetime(order_data.get("date_closed")),
            "date_last_updated": safe_datetime(order_data.get("date_last_updated")),
            "expiration_date": safe_datetime(order_data.get("expiration_date")),
            "total_amount": safe_decimal(order_data["total_amount"]),
            "paid_amount": safe_decimal(order_data["paid_amount"]),
            "currency_id": order_data["currency_id"],
            "shipping_cost": safe_decimal(order_data.get("shipping_cost")),
            "pack_id": order_data.get("pack_id"),
            "fulfilled": order_data.get("fulfilled"),
            "comment": order_data.get("comment"),
            "tags": order_data.get("tags"),
            "feedback_data": order_data.get("feedback"),
            "context_data": order_data.get("context"),
            "processing_time_hours": safe_decimal(processing_time),
        }

        # Transform order items
        items = []
        for item_data in order_data.get("order_items", []):
            item = item_data.get("item", {})
            items.append(
                {
                    "order_id": str(order_data["id"]),
                    "element_id": item_data.get("element_id"),
                    "item_id": item.get("id"),
                    "title": item.get("title"),
                    "category_id": item.get("category_id"),
                    "variation_id": (
                        str(item.get("variation_id"))
                        if item.get("variation_id")
                        else None
                    ),
                    "seller_sku": item.get("seller_sku"),
                    "quantity": item_data.get("quantity"),
                    "unit_price": safe_decimal(item_data.get("unit_price")),
                    "full_unit_price": safe_decimal(item_data.get("full_unit_price")),
                    "sale_fee": safe_decimal(item_data.get("sale_fee")),
                    "listing_type_id": item_data.get("listing_type_id"),
                    "condition": item.get("condition"),
                    "warranty": item.get("warranty"),
                    "variation_attributes": item.get("variation_attributes"),
                }
            )

        # Transform payments
        payments = []
        for payment_data in order_data.get("payments", []):
            payments.append(
                {
                    "id": str(payment_data["id"]),
                    "order_id": str(order_data["id"]),
                    "payer_id": payment_data.get("payer_id"),
                    "collector_id": payment_data.get("collector", {}).get("id"),
                    "status": payment_data["status"],
                    "status_detail": payment_data.get("status_detail"),
                    "payment_method_id": payment_data["payment_method_id"],
                    "payment_type": payment_data["payment_type"],
                    "operation_type": payment_data["operation_type"],
                    "transaction_amount": safe_decimal(
                        payment_data["transaction_amount"]
                    ),
                    "total_paid_amount": safe_decimal(
                        payment_data["total_paid_amount"]
                    ),
                    "transaction_amount_refunded": safe_decimal(
                        payment_data.get("transaction_amount_refunded")
                    ),
                    "date_created": safe_datetime(payment_data["date_created"]),
                    "date_approved": safe_datetime(payment_data.get("date_approved")),
                    "date_last_modified": safe_datetime(
                        payment_data.get("date_last_modified")
                    ),
                    "installments": payment_data.get("installments"),
                    "installment_amount": safe_decimal(
                        payment_data.get("installment_amount")
                    ),
                    "issuer_id": payment_data.get("issuer_id"),
                    "reason": payment_data.get("reason"),
                    "shipping_cost": safe_decimal(payment_data.get("shipping_cost")),
                    "taxes_amount": safe_decimal(payment_data.get("taxes_amount")),
                    "coupon_amount": safe_decimal(payment_data.get("coupon_amount")),
                }
            )

        return {"order": order, "items": items, "payments": payments}

    def load_batch(self, transformed_data_list: List[Dict]):
        """Load a batch of transformed data into the database"""
        try:
            for data in transformed_data_list:
                # Check if order already exists
                existing_order = (
                    self.session.query(Order).filter_by(id=data["order"]["id"]).first()
                )

                if existing_order:
                    # Update existing order
                    for key, value in data["order"].items():
                        setattr(existing_order, key, value)

                    # Delete existing items and payments to replace them
                    self.session.query(OrderItem).filter_by(
                        order_id=data["order"]["id"]
                    ).delete()
                    self.session.query(Payment).filter_by(
                        order_id=data["order"]["id"]
                    ).delete()
                else:
                    # Create new order
                    order = Order(**data["order"])
                    self.session.add(order)

                # Add items
                for item_data in data["items"]:
                    item = OrderItem(**item_data)
                    self.session.add(item)

                # Add payments
                for payment_data in data["payments"]:
                    payment = Payment(**payment_data)
                    self.session.add(payment)

            self.session.commit()
            self.logger.info(f"Successfully loaded {len(transformed_data_list)} orders")

        except SQLAlchemyError as e:
            self.logger.error(f"Database error during batch load: {e}")
            self.session.rollback()

            # Save failed data to JSON file for manual inspection
            failed_file = f"failed_orders_{int(time.time())}.json"
            with open(failed_file, "w") as f:
                json.dump(transformed_data_list, f, indent=2, default=str)
            self.logger.error(f"Failed data saved to {failed_file}")
            raise

    def run_pipeline(
        self,
        seller_id: int,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
    ):
        """Run the complete ETL pipeline"""
        start_time = time.time()
        total_orders = 0

        self.logger.info(f"Starting ETL pipeline for seller {seller_id}")
        self.logger.info(
            f"Date range: {start_date or 'earliest'} to {end_date or 'latest'}"
        )

        try:
            self.initialize_client()

            # Create progress bar
            pbar = tqdm(desc="Processing orders", unit="orders")

            for order_batch in self.fetch_all_orders(seller_id, start_date, end_date):
                # Transform the batch
                transformed_batch = []
                for order in order_batch:
                    try:
                        transformed = self.transform_order(order)
                        transformed_batch.append(transformed)
                    except Exception as e:
                        self.logger.error(
                            f"Failed to transform order {order.get('id', 'unknown')}: {e}"
                        )
                        continue

                # Load the batch
                if transformed_batch:
                    self.load_batch(transformed_batch)
                    total_orders += len(transformed_batch)
                    pbar.update(len(transformed_batch))

            pbar.close()

            # Mark as completed
            self._update_etl_state(seller_id, 0, total_orders, status="completed")

            duration = time.time() - start_time
            self.logger.info(f"Pipeline completed successfully!")
            self.logger.info(f"Total orders processed: {total_orders}")
            self.logger.info(f"Duration: {duration:.2f} seconds")

        except Exception as e:
            self.logger.error(f"Pipeline failed: {e}")
            self._update_etl_state(seller_id, 0, total_orders, status="failed")
            raise
        finally:
            self.session.close()

    def get_pipeline_stats(self, seller_id: int) -> Dict:
        """Get pipeline statistics"""
        stats = {}

        # Get ETL state
        state = self.session.query(ETLState).filter_by(seller_id=seller_id).first()
        if state:
            stats["etl_state"] = {
                "status": state.status,
                "total_processed": state.total_processed,
                "last_run": (
                    state.last_run_date.isoformat() if state.last_run_date else None
                ),
                "last_order_id": state.last_order_id,
            }

        # Get order counts by status
        status_counts = (
            self.session.query(Order.status, func.count(Order.id))
            .filter_by(seller_id=seller_id)
            .group_by(Order.status)
            .all()
        )
        stats["order_counts"] = dict(status_counts)

        # Get date range
        date_range = (
            self.session.query(
                func.min(Order.date_created), func.max(Order.date_created)
            )
            .filter_by(seller_id=seller_id)
            .first()
        )
        if date_range[0]:
            stats["date_range"] = {
                "earliest": date_range[0].isoformat(),
                "latest": date_range[1].isoformat(),
            }

        return stats


def main():
    parser = argparse.ArgumentParser(
        description="MercadoLibre Seller Orders ETL Pipeline"
    )
    parser.add_argument("--seller", required=True, type=int, help="Seller ID")
    parser.add_argument("--start-date", help="Start date (YYYY-MM-DD)")
    parser.add_argument("--end-date", help="End date (YYYY-MM-DD)")
    parser.add_argument(
        "--batch-size", type=int, default=100, help="Batch size for API calls"
    )
    parser.add_argument(
        "--db-path", default="./data/orders.db", help="SQLite database path"
    )
    parser.add_argument("--stats", action="store_true", help="Show pipeline statistics")

    args = parser.parse_args()

    # Create data directory if it doesn't exist
    os.makedirs(os.path.dirname(args.db_path), exist_ok=True)

    # Initialize ETL pipeline
    etl = MercadoLibreETL(args.db_path, args.batch_size)

    try:
        if args.stats:
            stats = etl.get_pipeline_stats(args.seller)
            print(json.dumps(stats, indent=2))
        else:
            etl.run_pipeline(args.seller, args.start_date, args.end_date)
    except KeyboardInterrupt:
        print("\nPipeline interrupted by user")
        etl._update_etl_state(args.seller, 0, 0, status="paused")
    except Exception as e:
        print(f"Pipeline failed: {e}")
        sys.exit(1)
    finally:
        etl.session.close()


if __name__ == "__main__":
    main()
