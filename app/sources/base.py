from datetime import date
from typing import Protocol

from app.domain import NormalizedDailyGoal, NormalizedFoodEntry


class NutritionSource(Protocol):
    name: str
    # True only when an empty/missing item in the requested date window means
    # it was actually deleted upstream, rather than merely omitted by a partial
    # response.
    authoritative_window: bool

    async def fetch_entries(
        self, start_date: date, end_date: date
    ) -> list[NormalizedFoodEntry]: ...

    async def fetch_daily_goals(
        self, start_date: date, end_date: date
    ) -> list[NormalizedDailyGoal]: ...
