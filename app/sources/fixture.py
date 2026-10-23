import json
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from app.domain import NormalizedDailyGoal, NormalizedFoodEntry, normalize_fixture_entry


class FixtureSource:
    name = "fixture"
    authoritative_window = True

    def __init__(self, timezone_name: str, fixture_path: Path | None = None):
        self.timezone_name = timezone_name
        self.fixture_path = fixture_path or Path(__file__).with_name(
            "fixture_data.json"
        )

    async def fetch_entries(
        self, start_date: date, end_date: date
    ) -> list[NormalizedFoodEntry]:
        payloads = json.loads(self.fixture_path.read_text(encoding="utf-8"))

        # The fixture is an onboarding aid, not a historical export. Shift its
        # synthetic anchor day to the requested end date so a fresh install
        # always returns useful sample data instead of aging into an empty sync.
        timezone = ZoneInfo(self.timezone_name)
        consumed_at = [
            datetime.fromisoformat(str(item["consumed_at"])) for item in payloads
        ]
        anchor_date = max(item.astimezone(timezone).date() for item in consumed_at)
        offset = timedelta(days=(end_date - anchor_date).days)
        shifted_payloads = []
        for payload, timestamp in zip(payloads, consumed_at, strict=True):
            shifted = dict(payload)
            shifted["consumed_at"] = (timestamp + offset).isoformat()
            shifted_payloads.append(shifted)

        entries = [
            normalize_fixture_entry(item, self.timezone_name)
            for item in shifted_payloads
        ]
        return [
            entry for entry in entries if start_date <= entry.local_date <= end_date
        ]

    async def fetch_daily_goals(
        self, start_date: date, end_date: date
    ) -> list[NormalizedDailyGoal]:
        # Fixture diary rows deliberately have no personal targets.  An absent
        # target must remain unknown rather than becoming an invented default.
        return []
