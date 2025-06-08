#!/usr/bin/env python3
"""
Script to retrieve seller IDs and nicknames from the Underwear category (MLB4954) on Mercado Livre.
Usage: Run the script and press Enter to retrieve the first 10 unique sellers, or type "max" to retrieve all available sellers.
"""

import os
import sys

# ─── Ensure that `src/` (the project root) is on PYTHONPATH ──────────────────
script_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.abspath(os.path.join(script_dir, os.pardir))
if project_root not in sys.path:
    sys.path.insert(0, project_root)
# ──────────────────────────────────────────────────────────────────────────────

from src.extractors.ml_api_client import create_client

CATEGORY_ID = "MLB4954"
PAGE_LIMIT = 50  # Maximum items per page (API limit)


def main():
    client, token = create_client()
    choice = (
        input("Press Enter to retrieve 10 sellers, or type 'max' to retrieve all: ")
        .strip()
        .lower()
    )

    seller_ids = set()
    offset = 0

    if choice == "max":
        print("Retrieving all sellers. This may take a while...")
        while True:
            # Fetch up to PAGE_LIMIT items per page, advancing by offset
            search_results = client.search(
                token,
                site_id="MLB",
                category=CATEGORY_ID,
                limit=PAGE_LIMIT,
                offset=offset,
            )
            items = search_results.get("results", [])
            if not items:
                break

            # Collect seller IDs from each item
            for item in items:
                seller_info = item.get("seller", {})
                seller_id = seller_info.get("id")
                if seller_id:
                    seller_ids.add(seller_id)

            offset += PAGE_LIMIT

        print(f"Total unique sellers found: {len(seller_ids)}")

    else:
        print("Retrieving first 10 unique sellers...")
        # Only fetch 10 items for a quick list
        search_results = client.search(
            token, site_id="MLB", category=CATEGORY_ID, limit=10, offset=0
        )
        items = search_results.get("results", [])
        for item in items:
            seller_info = item.get("seller", {})
            seller_id = seller_info.get("id")
            if seller_id:
                seller_ids.add(seller_id)

    # For each unique seller ID, fetch and display the nickname
    print("\nSeller ID\tNickname")
    print("-" * 40)
    for seller_id in list(seller_ids):
        try:
            user_data = client.get_user(token, user_id=seller_id)
            nickname = user_data.get("nickname", "N/A")
        except Exception as e:
            nickname = f"Error: {str(e)}"
        print(f"{seller_id}\t{nickname}")


if __name__ == "__main__":
    main()
