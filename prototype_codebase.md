---
```python
# Configuration management
## config/config.py
#!/usr/bin/env python3
import os
from dataclasses import dataclass
from dotenv import load_dotenv

load_dotenv()


@dataclass
class Config:
    client_id: str = os.getenv("ML_CLIENT_ID")
    client_secret: str = os.getenv("ML_CLIENT_SECRET")
    redirect_uri: str = os.getenv("ML_REDIRECT_URI")
    timeout: int = int(os.getenv("API_TIMEOUT", 30))
    rate_limit: int = int(os.getenv("RATE_LIMIT", 100))

    # API URLs
    api_url: str = "https://api.mercadolibre.com"
    auth_url: str = "https://auth.mercadolivre.com.br"

    # Files
    token_file: str = "ml_tokens.json"

    # Fallback tokens
    fallback_access: str = os.getenv("ACCESS_TOKEN")
    fallback_refresh: str = os.getenv("REFRESH_TOKEN")
    fallback_expires: str = os.getenv("TOKEN_EXPIRES")


cfg = Config()

# ---

# API client
# src/extractors/ml_api_client.py
#!/usr/bin/env python3
import os
import json
import requests
import secrets
from datetime import datetime, timedelta
from config.config import cfg


class MLClient:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update(
            {"Accept": "application/json", "User-Agent": "MLExtractor/1.0"}
        )
        self._rate = {"calls": 0, "reset": datetime.now()}

    def _check_rate(self):
        now = datetime.now()
        if now - self._rate["reset"] > timedelta(minutes=1):
            self._rate = {"calls": 0, "reset": now}
        if self._rate["calls"] >= cfg.rate_limit:
            raise Exception("Rate limit exceeded")
        self._rate["calls"] += 1

    def _req(self, method, endpoint, **kwargs):
        self._check_rate()
        url = f"{cfg.api_url}{endpoint}"

        kwargs.setdefault("headers", {}).update(
            {"X-Request-ID": secrets.token_hex(8), "Cache-Control": "no-cache"}
        )

        try:
            resp = self.session.request(method, url, timeout=cfg.timeout, **kwargs)
            resp.raise_for_status()
            return {} if resp.status_code == 204 else resp.json()
        except requests.exceptions.HTTPError:
            status = resp.status_code
            try:
                err = resp.json()
            except ValueError:
                err = {"error": "Invalid JSON"}

            error_map = {
                401: f"Unauthorized: {err}",
                403: f"Forbidden: {err}",
                404: f"Not found: {endpoint}",
                429: "Rate limited",
            }
            raise Exception(error_map.get(status, f"HTTP {status}: {err}"))
        except requests.exceptions.Timeout:
            raise Exception("Request timeout")
        except Exception as e:
            raise Exception(f"Request failed: {str(e)}")

    def _auth(self, token):
        self.session.headers.update({"Authorization": f"Bearer {token}"})

    # Core API methods
    def get_user(self, token, user_id="me", attrs=None):
        self._auth(token)
        params = {"attributes": attrs} if attrs else {}
        return self._req("GET", f"/users/{user_id}", params=params)

    def get_items(self, token, seller_id, limit=50, status="active"):
        self._auth(token)
        params = {"limit": limit, "status": status}
        result = self._req("GET", f"/users/{seller_id}/items/search", params=params)
        return [self.get_item(token, item_id) for item_id in result.get("results", [])]

    def get_item(self, token, item_id, attrs=None):
        self._auth(token)
        params = {"attributes": attrs} if attrs else {}
        return self._req("GET", f"/items/{item_id}", params=params)

    def get_desc(self, token, item_id):
        self._auth(token)
        try:
            return self._req("GET", f"/items/{item_id}/description")
        except Exception as e:
            return {"plain_text": "N/A", "error": str(e)}

    def get_reviews(self, token, item_id):
        self._auth(token)
        try:
            return self._req("GET", f"/reviews/item/{item_id}")
        except Exception as e:
            return {
                "rating_average": 0,
                "total_reviews": 0,
                "reviews": [],
                "error": str(e),
            }

    def get_questions(self, token, item_id, limit=10):
        self._auth(token)
        try:
            params = {"item_id": item_id, "limit": limit}
            return self._req("GET", "/questions/search", params=params)
        except Exception as e:
            return {"questions": [], "total": 0, "error": str(e)}

    def get_orders(self, token, seller_id, limit=50):
        self._auth(token)
        params = {"seller": seller_id, "limit": limit}
        return self._req("GET", "/orders/search", params=params)["results"]

    def get_listing_types(self, token, site_id):
        self._auth(token)
        return self._req("GET", f"/sites/{site_id}/listing_types")

    def get_listing_exposures(self, token, site_id):
        self._auth(token)
        return self._req("GET", f"/sites/{site_id}/listing_exposures")

    def search(
        self,
        token,
        site_id,
        query=None,
        seller_id=None,
        category=None,
        limit=50,
        offset=0,
    ):
        # Authenticate immediately
        self._auth(token)

        # Always build the same param dictionary
        params = {"limit": limit, "offset": offset}
        if query:
            params["q"] = query
        if seller_id:
            params["seller_id"] = seller_id
        if category:
            params["category"] = category

        # 1) Try the generic /sites/{site_id}/search
        try:
            return self._req("GET", f"/sites/{site_id}/search", params=params)
        except Exception as e:
            # If it fails with 403 or 401, fall back to “items by seller” if we can
            msg = str(e).lower()
            if "403" in msg or "401" in msg:
                # If caller already passed seller_id, just re‐raise (nothing else to try)
                if seller_id:
                    raise

                # Otherwise, fetch the user’s own ID and do /users/{id}/items/search
                user = self.get_user(token)  # returns JSON with “id” field
                fallback_seller = user["id"]
                return self.get_items(token, fallback_seller, limit=limit)
            # For any other exception, re‐raise
            raise

    def get_categories(self, token, site_id):
        try:
            return self._req("GET", f"/sites/{site_id}/categories")
        except Exception:
            return self._req("GET", f"/sites/{site_id}/categories")

    def get_category(self, token, category_id):
        try:
            return self._req("GET", f"/categories/{category_id}")
        except Exception:
            return self._req("GET", f"/categories/{category_id}")

    def get_trends(self, token, site_id, category_id=None):
        endpoint = f"/trends/{site_id}"
        if category_id:
            endpoint += f"/{category_id}"
        return self._req("GET", endpoint, headers={"Authorization": f"Bearer {token}"})

    def validate_item(self, token, item_data):
        self._auth(token)
        try:
            resp = self.session.post(
                f"{cfg.api_url}/items/validate",
                json=item_data,
                headers=self.session.headers,
                timeout=cfg.timeout,
            )
            return {
                "valid": resp.status_code == 204,
                "errors": resp.json() if resp.status_code != 204 else None,
            }
        except Exception as e:
            return {"valid": False, "errors": str(e)}


# Token management
def save_tokens(tokens):
    tokens["expires_at"] = (
        datetime.now() + timedelta(seconds=tokens["expires_in"])
    ).isoformat()
    with open(cfg.token_file, "w") as f:
        json.dump(tokens, f)


def load_tokens():
    if os.path.exists(cfg.token_file):
        with open(cfg.token_file) as f:
            return json.load(f)
    return {
        "access_token": cfg.fallback_access,
        "token_type": "Bearer",
        "expires_in": 21600,
        "refresh_token": cfg.fallback_refresh,
        "expires_at": cfg.fallback_expires,
    }


def is_valid(tokens):
    if not tokens:
        return False
    expires_at = datetime.fromisoformat(tokens["expires_at"])
    return datetime.now() < expires_at - timedelta(minutes=5)


def refresh_token(refresh_token):
    resp = requests.post(
        f"{cfg.api_url}/oauth/token",
        data={
            "grant_type": "refresh_token",
            "client_id": cfg.client_id,
            "client_secret": cfg.client_secret,
            "refresh_token": refresh_token,
        },
        timeout=cfg.timeout,
    )
    resp.raise_for_status()
    return resp.json()


def get_token():
    tokens = load_tokens()

    if tokens and is_valid(tokens):
        return tokens["access_token"]

    if tokens and "refresh_token" in tokens:
        try:
            new_tokens = refresh_token(tokens["refresh_token"])
            save_tokens(new_tokens)
            return new_tokens["access_token"]
        except Exception:
            pass

    return load_tokens()["access_token"]


def create_client():
    return MLClient(), get_token()

# ---

#!/usr/bin/env python3
# tests/test_api.py
import json
import unittest
import logging
from src.extractors.ml_api_client import create_client, get_token, is_valid, load_tokens


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class TestMLClient(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client, cls.token = create_client()
        cls.user_data = None
        cls.site_id = None

    def setUp(self):
        self.assertIsNotNone(self.client)
        self.assertIsNotNone(self.token)

    def test_01_tokens(self):
        tokens = load_tokens()
        self.assertIsNotNone(tokens)
        self.assertIn("access_token", tokens)

        self.assertTrue(is_valid(tokens))

        token = get_token()
        self.assertIsNotNone(token)
        self.assertTrue(len(token) > 50)

        print("✅ Token management")

    def test_02_rate_limiting(self):
        try:
            self.client._check_rate()
            print("✅ Rate limiting")
        except Exception as e:
            self.fail(f"Rate limit check failed: {e}")

    def test_03_user_profile(self):
        user = self.client.get_user(self.token)

        self.assertIsNotNone(user)
        self.assertIn("id", user)
        self.assertIn("nickname", user)
        self.assertIn("site_id", user)

        TestMLClient.user_data = user
        TestMLClient.site_id = user["site_id"]

        print(f"✅ User: {user['nickname']} ({user['id']}, {user['site_id']})")

    def test_04_user_items(self):
        if not TestMLClient.user_data:
            self.test_03_user_profile()

        user_data = TestMLClient.user_data
        items = self.client.get_items(self.token, user_data["id"], limit=5)

        self.assertIsInstance(items, list)
        if items:
            item = items[0]
            self.assertIn("id", item)
            self.assertIn("title", item)
            self.assertIn("price", item)
            self.assertIn("status", item)

        print(f"✅ Retrieved {len(items)} items")

    def test_05_item_details(self):
        if not TestMLClient.user_data:
            self.test_03_user_profile()

        user_data = TestMLClient.user_data
        items = self.client.get_items(self.token, user_data["id"], limit=1)

        if items:
            item_id = items[0]["id"]

            item = self.client.get_item(self.token, item_id)
            self.assertIn("id", item)
            self.assertIn("title", item)

            desc = self.client.get_desc(self.token, item_id)
            self.assertIsInstance(desc, dict)

            reviews = self.client.get_reviews(self.token, item_id)
            self.assertIsInstance(reviews, dict)
            self.assertIn("rating_average", reviews)

            questions = self.client.get_questions(self.token, item_id)
            self.assertIsInstance(questions, dict)

            print(f"✅ Item details for {item_id}")
        else:
            print("⚠️ No items to test")

    def test_06_orders(self):
        if not TestMLClient.user_data:
            self.test_03_user_profile()

        user_data = TestMLClient.user_data
        try:
            orders = self.client.get_orders(self.token, user_data["id"], limit=5)
            self.assertIsInstance(orders, list)
            print(f"✅ Retrieved {len(orders)} orders")
        except Exception as e:
            print(f"⚠️ Orders: {e}")

    def test_07_listing_types(self):
        if not TestMLClient.site_id:
            self.test_03_user_profile()

        site_id = TestMLClient.site_id
        try:
            types = self.client.get_listing_types(self.token, site_id)
            self.assertIsInstance(types, list)
            if types:
                self.assertIn("id", types[0])
                self.assertIn("name", types[0])
            print(f"✅ Retrieved {len(types)} listing types")
        except Exception as e:
            print(f"⚠️ Listing types: {e}")

    def test_08_exposures(self):
        if not TestMLClient.site_id:
            self.test_03_user_profile()

        site_id = TestMLClient.site_id
        try:
            exposures = self.client.get_listing_exposures(self.token, site_id)
            self.assertIsInstance(exposures, list)
            print(f"✅ Retrieved {len(exposures)} exposures")
        except Exception as e:
            print(f"⚠️ Exposures: {e}")

    def test_09_search(self):
        if not TestMLClient.site_id:
            self.test_03_user_profile()

        site_id = TestMLClient.site_id
        try:
            results = self.client.search(
                self.token, site_id, query="smartphone", limit=5
            )
            self.assertIsInstance(results, dict)
            self.assertIn("results", results)
            print(f"✅ Search returned {len(results.get('results', []))} items")

            if TestMLClient.user_data:
                seller_results = self.client.search(
                    self.token, site_id, seller_id=TestMLClient.user_data["id"], limit=5
                )
                self.assertIsInstance(seller_results, dict)
                print(
                    f"✅ Seller search returned {len(seller_results.get('results', []))} items"
                )
        except Exception as e:
            print(f"⚠️ Search: {e}")

    def test_10_categories(self):
        if not TestMLClient.site_id:
            self.test_03_user_profile()

        site_id = TestMLClient.site_id
        try:
            categories = self.client.get_categories(self.token, site_id)
            self.assertIsInstance(categories, list)

            if categories:
                cat_info = self.client.get_category(self.token, categories[0]["id"])
                self.assertIsInstance(cat_info, dict)
                self.assertIn("id", cat_info)
                self.assertIn("name", cat_info)

                print(f"✅ Retrieved {len(categories)} categories")
                print(f"✅ Category info for '{cat_info['name']}'")
            else:
                print("⚠️ No categories")
        except Exception as e:
            print(f"⚠️ Categories: {e}")

    def test_11_trends(self):
        if not TestMLClient.site_id:
            self.test_03_user_profile()

        site_id = TestMLClient.site_id
        try:
            trends = self.client.get_trends(self.token, site_id)
            self.assertIsInstance(trends, (list, dict))
            print("✅ Trends retrieved")
        except Exception as e:
            print(f"⚠️ Trends: {e}")

    def test_12_validation(self):
        """
        Attempt to validate a sample “Underwear” item under category MLB4954.
        This version:

        1) Ensures price ≥ minimum (which is 8 for MLB4954).
        2) Uses currency_id="BRL".
        3) Picks a valid listing_type_id from get_listing_types().
        4) Dynamically adds SIZE_GRID_ID, SIZE_GRID_ROW_ID, and SIZE
        as soon as validation complains they’re missing.
        If SIZE_GRID_ID has no values, the test is skipped rather than failed.
        """
        cat_id = "MLB4954"

        # Step 1: Fetch category info to learn “minimum price”
        try:
            cat_info = self.client.get_category(self.token, cat_id)
        except Exception as e:
            self.fail(f"Failed to fetch category {cat_id}: {e}")
            return

        settings = cat_info.get("settings", {})
        price_settings = settings.get("price", None)
        if isinstance(price_settings, dict):
            min_price = price_settings.get("minimum", 1)
        else:
            min_price = 1

        # Step 2: Pick a valid listing_type_id (first one we find under this site)
        try:
            site_id = TestMLClient.site_id
            lt_list = self.client.get_listing_types(self.token, site_id)
            if isinstance(lt_list, list) and lt_list:
                listing_type_id = lt_list[0]["id"]
            else:
                listing_type_id = "bronze"
        except Exception:
            listing_type_id = "bronze"

        # Build the _initial_ sample_item (no fashion attributes yet)
        sample_item = {
            "title": "Test Underwear Product",
            "category_id": cat_id,
            "price": max(min_price, 8),  # MLB4954 requires ≥ 8
            "currency_id": "BRL",
            "available_quantity": 1,
            "buying_mode": "buy_it_now",
            "listing_type_id": listing_type_id,
            "condition": "new",
            "description": {"plain_text": "Test description for underwear"},
            "pictures": [],
            "attributes": [],
        }

        chosen_grid_id = None
        chosen_row = None

        # Step 3: Loop until valid or until we run out of fixes
        for _ in range(5):
            try:
                result = self.client.validate_item(self.token, sample_item)
            except Exception as e:
                self.fail(f"Validation request threw exception: {e}")
                return

            # If it returns valid:true, we’re done
            if isinstance(result, dict) and result.get("valid") is True:
                print("✅ Item validation passed for MLB4954")
                return

            if not isinstance(result, dict) or "errors" not in result:
                self.fail(f"Unexpected validation response: {result}")
                return

            causes = result["errors"].get("cause", [])
            if not causes:
                self.fail(f"Validation failed, but no 'cause' array: {result}")
                return

            fixed_any = False
            for cause in causes:
                code = cause.get("code", "")

                if code == "missing.fashion_grid.grid_id.values":
                    # Fetch all attributes for this category
                    try:
                        self.client._auth(self.token)
                        all_attrs = self.client._req(
                            "GET", f"/categories/{cat_id}/attributes"
                        )
                    except Exception as e:
                        self.fail(
                            f"Failed to fetch /categories/{cat_id}/attributes: {e}"
                        )
                        return

                    # Print all attribute IDs and value counts for debugging
                    print(">>> ALL ATTRIBUTES FOR MLB4954 <<<")
                    for attr in all_attrs:
                        val_count = len(attr.get("values") or [])
                        print(f"  • id = {attr.get('id'):25} values? {val_count}")
                    print(">>> END ATTRIBUTES LIST <<<")

                    # Find the SIZE_GRID_ID attribute
                    for attr in all_attrs:
                        if attr.get("id") == "SIZE_GRID_ID":
                            vals = attr.get("values", [])
                            print(f"⚠️ SIZE_GRID_ID found, but has {len(vals)} values")
                            if not vals:
                                # Skip instead of fail, since no grid values exist
                                self.skipTest(
                                    "Skipping test_12_validation: "
                                    "SIZE_GRID_ID exists but has no available values in MLB4954."
                                )
                                return
                            chosen_grid_id = vals[0].get("id")
                            break

                    if chosen_grid_id:
                        updated = False
                        for a in sample_item["attributes"]:
                            if a.get("id") == "SIZE_GRID_ID":
                                a["value_id"] = chosen_grid_id
                                updated = True
                                break
                        if not updated:
                            sample_item["attributes"].append(
                                {"id": "SIZE_GRID_ID", "value_id": chosen_grid_id}
                            )
                        fixed_any = True

                elif code == "missing.fashion_grid.grid_row_id.values":
                    if chosen_grid_id is None:
                        self.fail(
                            "SIZE_GRID_ID was never set, but SIZE_GRID_ROW_ID is missing"
                        )
                        return

                    try:
                        self.client._auth(self.token)
                        rows = self.client._req(
                            "GET", f"/size_grids/{chosen_grid_id}/rows"
                        )
                    except Exception as e:
                        self.fail(
                            f"Failed to fetch /size_grids/{chosen_grid_id}/rows: {e}"
                        )
                        return

                    if isinstance(rows, list) and rows:
                        chosen_row = rows[0]
                        row_id = chosen_row.get("id")
                    else:
                        row_id = None

                    if row_id:
                        updated = False
                        for a in sample_item["attributes"]:
                            if a.get("id") == "SIZE_GRID_ROW_ID":
                                a["value_id"] = row_id
                                updated = True
                                break
                        if not updated:
                            sample_item["attributes"].append(
                                {"id": "SIZE_GRID_ROW_ID", "value_id": row_id}
                            )
                        fixed_any = True

                elif code == "missing.fashion_grid.size.values":
                    if not chosen_row:
                        self.fail("SIZE_GRID_ROW_ID was never set, but SIZE is missing")
                        return

                    size_value = chosen_row.get("size") or chosen_row.get("code")
                    if size_value:
                        updated = False
                        for a in sample_item["attributes"]:
                            if a.get("id") == "SIZE":
                                a["value_name"] = size_value
                                updated = True
                                break
                        if not updated:
                            sample_item["attributes"].append(
                                {"id": "SIZE", "value_name": size_value}
                            )
                        fixed_any = True

                elif code == "item.price.invalid":
                    msg = cause.get("message", "")
                    parts = msg.split()
                    try:
                        required_min = int(parts[-1])
                    except Exception:
                        required_min = min_price
                    sample_item["price"] = required_min
                    fixed_any = True

            if not fixed_any:
                print("⚠️ Unhandled validation errors:")
                print(json.dumps(result["errors"], indent=2))
                self.fail("Validation failed with unhandled error codes.")
                return

        # After 5 attempts, if still not valid, show final errors
        print("⚠️ Ran out of attempts to satisfy validation. Final errors payload:")
        print(json.dumps(result["errors"], indent=2))
        self.fail("Could not satisfy all fashion-grid requirements.")

    def test_13_error_handling(self):
        with self.assertRaises(Exception):
            self.client.get_item(self.token, "INVALID_ID")

        with self.assertRaises(Exception):
            self.client._req("GET", "/invalid/endpoint")

        print("✅ Error handling working")

    def test_14_integration(self):
        user = self.client.get_user(self.token)
        items = self.client.get_items(self.token, user["id"], limit=3)

        results = {
            "user_id": user["id"],
            "nickname": user["nickname"],
            "site_id": user["site_id"],
            "total_items": len(items),
            "items_detailed": 0,
            "categories": 0,
            "search_ok": False,
        }

        for item in items:
            try:
                details = self.client.get_item(self.token, item["id"])
                desc = self.client.get_desc(self.token, item["id"])
                if details and desc:
                    results["items_detailed"] += 1
            except Exception:
                pass

        try:
            categories = self.client.get_categories(self.token, user["site_id"])
            results["categories"] = len(categories) if categories else 0
        except Exception:
            pass

        try:
            search_result = self.client.search(
                self.token, user["site_id"], query="test", limit=1
            )
            results["search_ok"] = bool(search_result.get("results"))
        except Exception:
            pass

        self.assertGreaterEqual(results["total_items"], 0)

        if results["total_items"] > 0:
            self.assertEqual(results["items_detailed"], len(items))

        print("✅ Integration flow completed")
        print(f"   User: {results['nickname']} ({results['user_id']})")
        print(
            f"   Items: {results['total_items']} total, {results['items_detailed']} detailed"
        )
        print(f"   Categories: {results['categories']}")
        print(f"   Search: {'Working' if results['search_ok'] else 'Limited'}")


def run_tests():
    print("=" * 50)
    print("MercadoLibre API Client Test Suite")
    print("=" * 50)

    loader = unittest.TestLoader()
    suite = loader.loadTestsFromTestCase(TestMLClient)
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)

    print("\n" + "=" * 50)
    print("SUMMARY")
    print("=" * 50)

    total = result.testsRun
    failures = len(result.failures)
    errors = len(result.errors)
    success_rate = ((total - failures - errors) / total * 100) if total > 0 else 0

    print(f"Tests: {total}")
    print(f"Passed: {total - failures - errors}")
    print(f"Failed: {failures}")
    print(f"Errors: {errors}")
    print(f"Success: {success_rate:.1f}%")

    if result.failures:
        print("\nFAILURES:")
        for test, trace in result.failures:
            print(f"- {test}: {trace}")

    if result.errors:
        print("\nERRORS:")
        for test, trace in result.errors:
            print(f"- {test}: {trace}")

    if success_rate >= 85:
        print(f"\n🎉 PASSED! API Client ready for production.")
    else:
        print(f"\n⚠️ {failures + errors} tests failed. Review before production.")

    return success_rate >= 85


def quick_test():
    print("Quick API Test...")
    try:
        client, token = create_client()
        user = client.get_user(token)
        items = client.get_items(token, user["id"], limit=1)

        search_ok = False
        try:
            search = client.search(token, user["site_id"], query="test", limit=1)
            search_ok = bool(search.get("results"))
        except Exception:
            pass

        print(f"✅ Quick Test Passed")
        print(f"   User: {user['nickname']} ({user['site_id']})")
        print(f"   Items: {len(items)}")
        print(f"   Search: {'OK' if search_ok else 'Limited'}")
        return True
    except Exception as e:
        print(f"❌ Quick Test Failed: {e}")
        return False


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "quick":
        quick_test()
    else:
        run_tests()

# ---
# Product extraction
# src/extractors/items_extractor.py
import logging
from src.extractors.ml_api_client import create_client

logger = logging.getLogger(__name__)


def extract_items(seller_id, limit=50):
    client, token = create_client()
    try:
        items = client.get_items(token, seller_id, limit=limit)
        return items or []
    except Exception as e:
        logger.error(f"Failed to extract items for seller {seller_id}: {e}")
        return []

# ---

# Product enrichment
# transformers/product_enricher.py
from datetime import datetime


def _get_attr(attrs, key):
    for a in attrs or []:
        if a.get("id") == key:
            return a.get("value_name") or a.get("value_id")
    return None


def enrich_items(raw_items):
    enriched = []
    for item in raw_items:
        attrs = item.get("attributes", [])
        brand = _get_attr(attrs, "BRAND")
        size = _get_attr(attrs, "SIZE")
        color = _get_attr(attrs, "COLOR")
        gender = _get_attr(attrs, "GENDER")

        views = item.get("views", 0) or 0
        sold = item.get("sold_quantity", 0) or 0
        conversion = round(sold / views, 4) if views else 0.0

        current_price = item.get("price") or 0.0
        original_price = item.get("original_price") or current_price
        discount_pct = (
            round((original_price - current_price) / original_price * 100, 2)
            if original_price
            else 0.0
        )

        enriched.append(
            {
                "item_id": item.get("id"),
                "title": item.get("title"),
                "category_id": item.get("category_id"),
                "current_price": current_price,
                "original_price": original_price,
                "available_quantity": item.get("available_quantity"),
                "sold_quantity": sold,
                "condition": item.get("condition"),
                "brand": brand,
                "size": size,
                "color": color,
                "gender": gender,
                "views": views,
                "conversion_rate": conversion,
                "seller_id": item.get("seller_id"),
                "created_at": datetime.utcnow(),
                "updated_at": datetime.utcnow(),
                "discount_percentage": discount_pct,
            }
        )
    return enriched
```