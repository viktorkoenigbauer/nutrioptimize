import unittest
from datetime import date
from decimal import Decimal

from app.domain import aggregate_nutrients, normalize_fixture_entry


class DomainTests(unittest.TestCase):
    def test_local_date_uses_vienna_timezone(self):
        payload = {
            "id": "near-midnight",
            "consumed_at": "2026-10-15T23:30:00+00:00",
            "meal": "snack",
            "food_name": "Apfel",
            "quantity": 1,
            "unit": "piece",
            "nutrients": {"energy_kcal": 80},
        }

        entry = normalize_fixture_entry(payload, "Europe/Vienna")

        self.assertEqual(entry.local_date, date(2026, 10, 16))

    def test_totals_keep_units_and_decimal_precision(self):
        base = {
            "consumed_at": "2026-10-15T08:00:00+02:00",
            "meal": "breakfast",
            "food_name": "Example",
            "quantity": 1,
            "unit": "serving",
        }
        first = normalize_fixture_entry(
            dict(base, id="one", nutrients={"protein_g": "1.15"}), "Europe/Vienna"
        )
        second = normalize_fixture_entry(
            dict(base, id="two", nutrients={"protein_g": "2.25"}), "Europe/Vienna"
        )

        totals = aggregate_nutrients([first, second])

        self.assertEqual(totals["protein_g"]["amount"], Decimal("3.40"))
        self.assertEqual(totals["protein_g"]["unit"], "g")

    def test_unknown_nutrient_is_rejected(self):
        payload = {
            "id": "bad-code",
            "consumed_at": "2026-10-15T08:00:00+02:00",
            "meal": "breakfast",
            "food_name": "Example",
            "nutrients": {"mystery": 1},
        }

        with self.assertRaisesRegex(ValueError, "Unknown nutrient code"):
            normalize_fixture_entry(payload, "Europe/Vienna")


if __name__ == "__main__":
    unittest.main()
