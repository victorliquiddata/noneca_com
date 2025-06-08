#!/usr/bin/env python3
"""
Standalone debugging test for MLClient authorization and basic endpoints.
"""
import argparse
import sys
import os

# Ensure project root for imports
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, PROJECT_ROOT)

from src.extractors.ml_api_client import create_client


def test_client_methods(site_id, seller_id):
    client, token = create_client()
    print(f"Testing MLClient with site_id={site_id}, seller_id={seller_id}\n")

    # Test get_user (default 'me') and by seller_id
    try:
        me = client.get_user(token)
        print("get_user('me') succeeded:")
        print(me)
    except Exception as e:
        print(f"get_user('me') failed: {e}")

    try:
        user = client.get_user(token, user_id=seller_id)
        print(f"get_user(seller_id={seller_id}) succeeded:")
        print(user)
    except Exception as e:
        print(f"get_user(seller_id) failed: {e}")

    # Compare returned user site_id to provided
    returned_site = user.get("site_id")
    if returned_site and returned_site != site_id:
        print(
            f"Warning: provided site_id '{site_id}' does not match user's site_id '{returned_site}'\n"
        )

    # Test search
    try:
        resp = client.search(
            token, site_id=site_id, seller_id=seller_id, limit=5, offset=0
        )
        results = resp.get("results", [])
        print(f"search() returned {len(results)} items (showing up to 5):")
        for item in results:
            print(f" - {item.get('id')}")
    except Exception as e:
        print(f"search() failed: {e}")

    # Test orders
    try:
        orders = client.get_orders(token, seller_id=seller_id, limit=5)
        print(f"get_orders() returned {len(orders)} orders (showing up to 5):")
        for order in orders:
            print(f" - {order.get('id')}")
    except Exception as e:
        print(f"get_orders() failed: {e}")


def main():
    parser = argparse.ArgumentParser(description="Test MLClient access and endpoints")
    parser.add_argument(
        "--site", required=True, help="MercadoLibre site ID (e.g. MLB, MLA)"
    )
    parser.add_argument("--seller", required=True, help="Seller user ID to test")
    args = parser.parse_args()

    test_client_methods(args.site, args.seller)


if __name__ == "__main__":
    main()
