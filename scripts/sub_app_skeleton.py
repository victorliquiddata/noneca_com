#!/usr/bin/env python3
"""
Skeleton creator for the orders_pipeline_app directory structure.

Usage:
    python create_pipeline_skeleton.py

This script creates the following layout:

orders_pipeline_app/
├── main.py
├── config.py
├── requirements.txt
├── README.md
└── src/
    ├── extractors/
    │   ├── ml_api_client.py
    │   └── orders.py
    ├── transform/
    │   └── orders.py
    ├── load/
    │   └── sqlite_loader.py
    └── models.py

Each file is created with a basic placeholder docstring.
"""
import os
import pathlib

# Root folder for the pipeline app
target_root = pathlib.Path("orders_pipeline_app")


def create_file(path: pathlib.Path, content: str = ""):
    """Helper to create a file with given content."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)


# Define directory structure and file stubs
structure = {
    "main.py": '#!/usr/bin/env python3\n"""Main entry point for the orders pipeline."""\n',
    "config.py": '"""Configuration defaults and environment loader."""\n',
    "requirements.txt": "# Add your project dependencies here",
    "README.md": "# Orders Pipeline App\n\nProject skeleton created by create_pipeline_skeleton.py",
    "src/extractors/ml_api_client.py": '"""Re-used MercadoLibre API client."""\n',
    "src/extractors/orders.py": '"""Fetch orders pagination module."""\n',
    "src/transform/orders.py": '"""Order normalization and enrichment module."""\n',
    "src/load/sqlite_loader.py": '"""SQLite loader with upsert functionality."""\n',
    "src/models.py": '"""SQLAlchemy ORM models and Alembic definitions."""\n',
}


def main():
    print(f"Creating pipeline skeleton under '{target_root}'...")
    for rel_path, stub in structure.items():
        file_path = target_root / rel_path
        if file_path.exists():
            print(f"Skipping existing file: {file_path}")
        else:
            create_file(file_path, stub)
            print(f"Created: {file_path}")
    print("Skeleton creation complete.")


if __name__ == "__main__":
    main()
