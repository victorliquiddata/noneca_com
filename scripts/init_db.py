# scripts/init_db.py
import os
import sys

# Add the parent directory (project root) to sys.path
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from sqlalchemy import create_engine, inspect
from src.models.models import create_all_tables


def main():
    db_url = "sqlite:///./noneca_analytics.db"
    engine = create_engine(db_url, future=True)
    create_all_tables(engine)

    inspector = inspect(engine)
    print("Tables in SQLite now:", inspector.get_table_names())


if __name__ == "__main__":
    main()
