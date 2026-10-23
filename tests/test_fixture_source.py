import unittest
from datetime import date

from app.sources.fixture import FixtureSource


class FixtureSourceTests(unittest.IsolatedAsyncioTestCase):
    async def test_sample_entries_follow_the_requested_end_date(self):
        source = FixtureSource("Europe/Vienna")
        end_date = date(2032, 4, 20)

        entries = await source.fetch_entries(end_date, end_date)

        self.assertEqual(len(entries), 4)
        self.assertEqual({entry.local_date for entry in entries}, {end_date})
        self.assertEqual(
            {entry.external_id for entry in entries},
            {
                "fixture-breakfast-1",
                "fixture-lunch-1",
                "fixture-dinner-1",
                "fixture-snack-1",
            },
        )


if __name__ == "__main__":
    unittest.main()
