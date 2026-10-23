import unittest
import uuid
from datetime import UTC, date, datetime
from decimal import Decimal

from app.models import DailyGoal, DailyGoalValue, FoodEntry, NutrientValue
from app.query_service import build_range_response


class QueryServiceTests(unittest.TestCase):
    def test_range_includes_empty_calendar_days(self):
        entry_id = uuid.uuid4()
        entry = FoodEntry(
            id=entry_id,
            source="fixture",
            external_id="one",
            consumed_at=datetime(2026, 10, 15, 8, tzinfo=UTC),
            local_date=date(2026, 10, 15),
            timezone="Europe/Vienna",
            meal="breakfast",
            food_name="Porridge",
            quantity=Decimal(300),
            unit="g",
            payload_hash="0" * 64,
            raw_payload={},
            nutrients=[
                NutrientValue(
                    entry_id=entry_id,
                    code="protein_g",
                    amount=Decimal("20.5"),
                    unit="g",
                )
            ],
        )

        response = build_range_response([entry], date(2026, 10, 15), date(2026, 10, 17))

        self.assertEqual(
            [day["date"] for day in response["days"]],
            ["2026-10-15", "2026-10-16", "2026-10-17"],
        )
        self.assertTrue(response["days"][0]["has_data"])
        self.assertEqual(response["days"][0]["entry_count"], 1)
        self.assertFalse(response["days"][1]["has_data"])
        self.assertEqual(response["days"][1]["totals"], {})
        self.assertIsNone(response["days"][1]["targets"])

    def test_range_includes_yazio_daily_targets_without_calling_them_tdee(self):
        goal_id = uuid.uuid4()
        goal = DailyGoal(
            id=goal_id,
            source="yazio",
            local_date=date(2026, 10, 15),
            timezone="Europe/Vienna",
            activity_energy_kcal=Decimal("410"),
            consume_activity_energy=True,
            payload_hash="1" * 64,
            raw_payload={},
            values=[
                DailyGoalValue(
                    daily_goal_id=goal_id,
                    variant="effective",
                    code="energy_kcal",
                    amount=Decimal("2350"),
                    unit="kcal",
                ),
                DailyGoalValue(
                    daily_goal_id=goal_id,
                    variant="unmodified",
                    code="energy_kcal",
                    amount=Decimal("2500"),
                    unit="kcal",
                ),
            ],
        )

        response = build_range_response(
            [], date(2026, 10, 15), date(2026, 10, 16), [goal]
        )

        targets = response["days"][0]["targets"]
        self.assertEqual(targets["effective"]["energy_kcal"]["amount"], 2350.0)
        self.assertEqual(targets["unmodified"]["energy_kcal"]["amount"], 2500.0)
        self.assertEqual(targets["activity_energy_kcal"], 410.0)
        self.assertTrue(targets["consume_activity_energy"])
        self.assertIsNone(response["days"][1]["targets"])


if __name__ == "__main__":
    unittest.main()
