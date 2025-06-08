#!/usr/bin/env python3
"""
Script to fetch the last two orders of a MercadoLibre seller for testing purposes.
"""
import argparse
import json
import sys
import os

# Ensure project root for imports
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, PROJECT_ROOT)

from src.extractors.ml_api_client import create_client


def fetch_last_two_orders(seller_id):
    """
    Initialize the ML client and fetch the last two orders for the given seller.

    Args:
        seller_id (str): The MercadoLibre seller ID.

    Returns:
        list: A list of up to two order dicts (most recent first).
    """
    client, token = create_client()
    # MercadoLibre API returns newest orders first when using get_orders()
    orders = client.get_orders(token, seller_id=seller_id, limit=2)
    return orders


def main():
    parser = argparse.ArgumentParser(
        description="Fetch the last two orders of a MercadoLibre seller and print as JSON"
    )
    parser.add_argument(
        "--seller", required=True, help="Seller user ID to fetch orders for"
    )
    args = parser.parse_args()

    try:
        last_two = fetch_last_two_orders(args.seller)
        # Output JSON to stdout
        print(json.dumps({"orders": last_two}, indent=2))
    except Exception as e:
        print(f"Error fetching orders: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
