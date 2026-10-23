import json
import unittest
from datetime import date
from decimal import Decimal

import httpx

from app.sources.yazio import YazioClientVersionBlocked, YazioSource


def source_with(client: httpx.AsyncClient) -> YazioSource:
    return YazioSource(
        timezone_name="Europe/Vienna",
        email="person@example.test",
        password="not-a-real-password",
        client_id="test-client",
        client_secret="test-client-secret",
        user_agent="YAZIO/test",
        http_client=client,
    )


class YazioSourceTests(unittest.IsolatedAsyncioTestCase):
    async def test_reads_and_normalizes_products_recipes_and_quick_entries(self):
        seen_authorization = []

        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/v22/oauth/token":
                return httpx.Response(
                    200,
                    json={
                        "access_token": "access-one",
                        "refresh_token": "refresh-one",
                        "expires_in": 3600,
                    },
                )

            seen_authorization.append(request.headers.get("authorization"))
            if request.url.path == "/v22/user/consumed-items":
                if request.url.params["date"] == "2026-10-15":
                    return httpx.Response(
                        200,
                        json={
                            "products": [
                                {
                                    "id": "entry-product",
                                    "product_id": "product-one",
                                    "date": "2026-10-15 08:30:00",
                                    "daytime": "breakfast",
                                    "amount": 50,
                                }
                            ],
                            "recipe_portions": [
                                {
                                    "id": "entry-recipe",
                                    "recipe_id": "recipe-one",
                                    "date": "2026-10-15 12:15:00",
                                    "daytime": "lunch",
                                    "portion_count": 2,
                                }
                            ],
                            "simple_products": [
                                {
                                    "id": "entry-simple",
                                    "name": "Quick snack",
                                    "date": "2026-10-15 16:00:00",
                                    "daytime": "snack",
                                    "nutrients": {
                                        "energy.energy": 80,
                                        "nutrient.protein": 0.01,
                                    },
                                }
                            ],
                        },
                    )
                return httpx.Response(404)
            if request.url.path == "/v22/products/product-one":
                return httpx.Response(
                    200,
                    json={
                        "name": "Example product",
                        "base_unit": "g",
                        "nutrients": {
                            "energy.energy": 2,
                            "nutrient.protein": 0.1,
                            "mineral.iron": 0.00001,
                        },
                    },
                )
            if request.url.path == "/v22/recipes/recipe-one":
                return httpx.Response(
                    200,
                    json={
                        "name": "Example recipe",
                        "nutrients": {
                            "energy.energy": 250,
                            "nutrient.protein": 0.02,
                        },
                    },
                )
            return httpx.Response(500)

        transport = httpx.MockTransport(handler)
        async with httpx.AsyncClient(
            transport=transport, base_url="https://yzapi.example.test"
        ) as client:
            entries = await source_with(client).fetch_entries(
                date(2026, 10, 15), date(2026, 10, 16)
            )

        self.assertEqual(len(entries), 3)
        self.assertTrue(
            all(value == "Bearer access-one" for value in seen_authorization)
        )

        product = next(item for item in entries if item.food_name == "Example product")
        self.assertEqual(product.external_id, "product:entry-product")
        self.assertEqual(product.quantity, Decimal("50"))
        self.assertEqual(product.unit, "g")
        product_nutrients = {item.code: item.amount for item in product.nutrients}
        self.assertEqual(product_nutrients["energy_kcal"], Decimal("100"))
        self.assertEqual(product_nutrients["protein_g"], Decimal("5.0"))
        self.assertEqual(product_nutrients["iron_mg"], Decimal("0.50000"))

        recipe = next(item for item in entries if item.food_name == "Example recipe")
        recipe_nutrients = {item.code: item.amount for item in recipe.nutrients}
        self.assertEqual(recipe_nutrients["energy_kcal"], Decimal("500"))
        self.assertEqual(recipe.quantity, Decimal("2"))

        quick = next(item for item in entries if item.food_name == "Quick snack")
        quick_nutrients = {item.code: item.amount for item in quick.nutrients}
        self.assertEqual(quick_nutrients["energy_kcal"], Decimal("80"))
        self.assertEqual(quick_nutrients["protein_g"], Decimal("0.01"))
        self.assertEqual(quick.local_date, date(2026, 10, 15))

    async def test_reads_effective_unmodified_and_activity_daily_goals(self):
        requested_paths = []

        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/v22/oauth/token":
                return httpx.Response(200, json={"access_token": "access-one"})
            requested_paths.append(request.url.path)
            self.assertEqual(request.url.params["date"], "2026-10-15")
            if request.url.path == "/v22/user/widgets/daily-summary":
                return httpx.Response(
                    200,
                    json={
                        "goals": {
                            "energy.energy": 2350,
                            "nutrient.protein": 125,
                            "nutrient.fat": 78,
                            "nutrient.carb": 265,
                        },
                        "activity_energy": 410,
                        "consume_activity_energy": True,
                        "user": {"email": "must-not-be-persisted@example.test"},
                    },
                )
            if request.url.path == "/v22/user/goals/unmodified":
                return httpx.Response(
                    200,
                    json={
                        "energy.energy": 2500,
                        "nutrient.protein": 130,
                        "nutrient.fat": 83,
                        "nutrient.carb": 280,
                    },
                )
            return httpx.Response(500)

        transport = httpx.MockTransport(handler)
        async with httpx.AsyncClient(
            transport=transport, base_url="https://yzapi.example.test"
        ) as client:
            goals = await source_with(client).fetch_daily_goals(
                date(2026, 10, 15), date(2026, 10, 15)
            )

        self.assertEqual(
            requested_paths,
            [
                "/v22/user/widgets/daily-summary",
                "/v22/user/goals/unmodified",
            ],
        )
        self.assertEqual(len(goals), 1)
        goal = goals[0]
        effective = {item.code: item.amount for item in goal.effective}
        unmodified = {item.code: item.amount for item in goal.unmodified}
        self.assertEqual(effective["energy_kcal"], Decimal("2350"))
        self.assertEqual(effective["protein_g"], Decimal("125"))
        self.assertEqual(unmodified["energy_kcal"], Decimal("2500"))
        self.assertEqual(goal.activity_energy_kcal, Decimal("410"))
        self.assertTrue(goal.consume_activity_energy)
        self.assertNotIn("user", goal.raw_payload)
        self.assertNotIn("must-not-be-persisted", str(goal.raw_payload))

    async def test_falls_back_to_direct_effective_goal_endpoint(self):
        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/v22/oauth/token":
                return httpx.Response(200, json={"access_token": "access-one"})
            if request.url.path == "/v22/user/widgets/daily-summary":
                return httpx.Response(404)
            if request.url.path == "/v22/user/goals":
                return httpx.Response(200, json={"data": {"energy": 2100}})
            if request.url.path == "/v22/user/goals/unmodified":
                return httpx.Response(200, json={"energy.energy": 2200})
            return httpx.Response(500)

        transport = httpx.MockTransport(handler)
        async with httpx.AsyncClient(
            transport=transport, base_url="https://yzapi.example.test"
        ) as client:
            goals = await source_with(client).fetch_daily_goals(
                date(2026, 10, 15), date(2026, 10, 15)
            )

        effective = {item.code: item.amount for item in goals[0].effective}
        self.assertEqual(effective["energy_kcal"], Decimal("2100"))
        self.assertIsNone(goals[0].activity_energy_kcal)
        self.assertIsNone(goals[0].consume_activity_energy)

    async def test_refreshes_once_after_unauthorized_response(self):
        token_requests = []
        diary_requests = 0

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal diary_requests
            if request.url.path == "/v22/oauth/token":
                body = json.loads(request.content)
                token_requests.append(body["grant_type"])
                if body["grant_type"] == "password":
                    return httpx.Response(
                        200,
                        json={
                            "access_token": "stale",
                            "refresh_token": "refresh-one",
                        },
                    )
                return httpx.Response(200, json={"access_token": "fresh"})
            if request.url.path == "/v22/user/consumed-items":
                diary_requests += 1
                if request.headers["authorization"] == "Bearer stale":
                    return httpx.Response(401)
                return httpx.Response(
                    200,
                    json={
                        "products": [],
                        "recipe_portions": [],
                        "simple_products": [],
                    },
                )
            return httpx.Response(500)

        transport = httpx.MockTransport(handler)
        async with httpx.AsyncClient(
            transport=transport, base_url="https://yzapi.example.test"
        ) as client:
            entries = await source_with(client).fetch_entries(
                date(2026, 10, 15), date(2026, 10, 15)
            )

        self.assertEqual(entries, [])
        self.assertEqual(token_requests, ["password", "refresh_token"])
        self.assertEqual(diary_requests, 2)

    async def test_reports_client_version_block_without_response_body(self):
        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/v22/oauth/token":
                return httpx.Response(200, json={"access_token": "token"})
            return httpx.Response(
                403,
                json={"error": "version_blocked", "private": "must-not-leak"},
            )

        transport = httpx.MockTransport(handler)
        async with httpx.AsyncClient(
            transport=transport, base_url="https://yzapi.example.test"
        ) as client:
            with self.assertRaises(YazioClientVersionBlocked) as raised:
                await source_with(client).fetch_entries(
                    date(2026, 10, 15), date(2026, 10, 15)
                )

        self.assertNotIn("must-not-leak", str(raised.exception))


if __name__ == "__main__":
    unittest.main()
