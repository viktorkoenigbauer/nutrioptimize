from datetime import date, timedelta
from typing import Any

from app.repository import (
    latest_sync_run,
    list_daily_goals,
    list_entries,
    serialize_daily_goal,
    serialize_sync_run,
    summarize_entries,
)


def build_range_response(
    entries, start_date: date, end_date: date, goals=()
) -> dict[str, Any]:
    entries_by_day = {}
    for entry in entries:
        entries_by_day.setdefault(entry.local_date, []).append(entry)

    goals_by_day = {goal.local_date: serialize_daily_goal(goal) for goal in goals}

    days = []
    cursor = start_date
    while cursor <= end_date:
        summary = summarize_entries(entries_by_day.get(cursor, []))
        summary["date"] = cursor.isoformat()
        summary["entry_count"] = len(summary["entries"])
        summary["has_data"] = summary["entry_count"] > 0
        summary["targets"] = goals_by_day.get(cursor)
        days.append(summary)
        cursor += timedelta(days=1)

    return {
        "start_date": start_date.isoformat(),
        "end_date": end_date.isoformat(),
        "days": days,
    }


async def get_sync_status(session_factory) -> dict[str, Any]:
    async with session_factory() as session:
        return serialize_sync_run(await latest_sync_run(session))


async def get_day(session_factory, day: date) -> dict[str, Any]:
    async with session_factory() as session:
        result = summarize_entries(await list_entries(session, day, day))
        goals = await list_daily_goals(session, day, day)
    result["date"] = day.isoformat()
    result["entry_count"] = len(result["entries"])
    result["has_data"] = result["entry_count"] > 0
    result["targets"] = serialize_daily_goal(goals[0]) if goals else None
    return result


async def get_range(
    session_factory, start_date: date, end_date: date
) -> dict[str, Any]:
    if start_date > end_date:
        raise ValueError("start_date must be before or equal to end_date")
    if (end_date - start_date).days > 92:
        raise ValueError("A single query may cover at most 93 days")

    async with session_factory() as session:
        entries = await list_entries(session, start_date, end_date)
        goals = await list_daily_goals(session, start_date, end_date)

    return build_range_response(entries, start_date, end_date, goals)
