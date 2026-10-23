from collections.abc import Iterable
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.domain import NormalizedDailyGoal, NormalizedFoodEntry
from app.models import DailyGoal, DailyGoalValue, FoodEntry, NutrientValue, SyncRun


async def upsert_food_entry(
    session: AsyncSession, normalized: NormalizedFoodEntry
) -> bool:
    existing_hash = await session.scalar(
        select(FoodEntry.payload_hash).where(
            FoodEntry.source == normalized.source,
            FoodEntry.external_id == normalized.external_id,
        )
    )
    changed = existing_hash != normalized.payload_hash

    statement = (
        insert(FoodEntry)
        .values(
            source=normalized.source,
            external_id=normalized.external_id,
            consumed_at=normalized.consumed_at,
            local_date=normalized.local_date,
            timezone=normalized.timezone,
            meal=normalized.meal,
            food_name=normalized.food_name,
            quantity=normalized.quantity,
            unit=normalized.unit,
            payload_hash=normalized.payload_hash,
            raw_payload=dict(normalized.raw_payload),
        )
        .on_conflict_do_update(
            constraint="uq_food_entries_source_external_id",
            set_={
                "consumed_at": normalized.consumed_at,
                "local_date": normalized.local_date,
                "timezone": normalized.timezone,
                "meal": normalized.meal,
                "food_name": normalized.food_name,
                "quantity": normalized.quantity,
                "unit": normalized.unit,
                "payload_hash": normalized.payload_hash,
                "raw_payload": dict(normalized.raw_payload),
                "updated_at": datetime.now(UTC),
            },
        )
        .returning(FoodEntry.id)
    )
    entry_id = (await session.execute(statement)).scalar_one()

    if changed:
        await session.execute(
            delete(NutrientValue).where(NutrientValue.entry_id == entry_id)
        )
        session.add_all(
            [
                NutrientValue(
                    entry_id=entry_id,
                    code=item.code,
                    amount=item.amount,
                    unit=item.unit,
                )
                for item in normalized.nutrients
            ]
        )
    return changed


async def delete_missing_food_entries(
    session: AsyncSession,
    *,
    source: str,
    start_date: date,
    end_date: date,
    external_ids: set[str],
) -> int:
    """Delete source rows absent from an authoritative upstream date window."""

    statement = delete(FoodEntry).where(
        FoodEntry.source == source,
        FoodEntry.local_date >= start_date,
        FoodEntry.local_date <= end_date,
    )
    if external_ids:
        statement = statement.where(FoodEntry.external_id.not_in(external_ids))
    result = await session.execute(statement)
    return int(result.rowcount or 0)


async def upsert_daily_goal(
    session: AsyncSession, normalized: NormalizedDailyGoal
) -> bool:
    existing_hash = await session.scalar(
        select(DailyGoal.payload_hash).where(
            DailyGoal.source == normalized.source,
            DailyGoal.local_date == normalized.local_date,
        )
    )
    changed = existing_hash != normalized.payload_hash

    statement = (
        insert(DailyGoal)
        .values(
            source=normalized.source,
            local_date=normalized.local_date,
            timezone=normalized.timezone,
            activity_energy_kcal=normalized.activity_energy_kcal,
            consume_activity_energy=normalized.consume_activity_energy,
            payload_hash=normalized.payload_hash,
            raw_payload=dict(normalized.raw_payload),
        )
        .on_conflict_do_update(
            constraint="uq_daily_goals_source_local_date",
            set_={
                "timezone": normalized.timezone,
                "activity_energy_kcal": normalized.activity_energy_kcal,
                "consume_activity_energy": normalized.consume_activity_energy,
                "payload_hash": normalized.payload_hash,
                "raw_payload": dict(normalized.raw_payload),
                "updated_at": datetime.now(UTC),
            },
        )
        .returning(DailyGoal.id)
    )
    goal_id = (await session.execute(statement)).scalar_one()

    if changed:
        await session.execute(
            delete(DailyGoalValue).where(DailyGoalValue.daily_goal_id == goal_id)
        )
        session.add_all(
            [
                DailyGoalValue(
                    daily_goal_id=goal_id,
                    variant=variant,
                    code=item.code,
                    amount=item.amount,
                    unit=item.unit,
                )
                for variant, values in (
                    ("effective", normalized.effective),
                    ("unmodified", normalized.unmodified),
                )
                for item in values
            ]
        )
    return changed


async def list_entries(
    session: AsyncSession, start_date: date, end_date: date
) -> list[FoodEntry]:
    statement = (
        select(FoodEntry)
        .where(FoodEntry.local_date >= start_date, FoodEntry.local_date <= end_date)
        .options(selectinload(FoodEntry.nutrients))
        .order_by(FoodEntry.consumed_at)
    )
    return list((await session.scalars(statement)).all())


async def list_daily_goals(
    session: AsyncSession, start_date: date, end_date: date
) -> list[DailyGoal]:
    statement = (
        select(DailyGoal)
        .where(DailyGoal.local_date >= start_date, DailyGoal.local_date <= end_date)
        .options(selectinload(DailyGoal.values))
        .order_by(DailyGoal.local_date)
    )
    return list((await session.scalars(statement)).all())


async def latest_sync_run(session: AsyncSession) -> SyncRun | None:
    return await session.scalar(
        select(SyncRun).order_by(SyncRun.started_at.desc()).limit(1)
    )


def _number(value: Decimal | None) -> float | None:
    return float(value) if value is not None else None


def serialize_entry(entry: FoodEntry) -> dict[str, Any]:
    return {
        "id": str(entry.id),
        "source": entry.source,
        "external_id": entry.external_id,
        "consumed_at": entry.consumed_at.isoformat(),
        "local_date": entry.local_date.isoformat(),
        "meal": entry.meal,
        "food_name": entry.food_name,
        "quantity": _number(entry.quantity),
        "unit": entry.unit,
        "nutrients": {
            item.code: {"amount": _number(item.amount), "unit": item.unit}
            for item in entry.nutrients
        },
    }


def summarize_entries(entries: Iterable[FoodEntry]) -> dict[str, Any]:
    serialized = [serialize_entry(item) for item in entries]
    totals = {}
    for entry in serialized:
        for code, nutrient in entry["nutrients"].items():
            current = totals.setdefault(code, {"amount": 0.0, "unit": nutrient["unit"]})
            if current["unit"] != nutrient["unit"]:
                raise ValueError(f"Unit mismatch for {code}")
            current["amount"] = round(current["amount"] + nutrient["amount"], 4)
    return {"entries": serialized, "totals": totals}


def serialize_daily_goal(goal: DailyGoal) -> dict[str, Any]:
    variants: dict[str, dict[str, dict[str, Any]]] = {
        "effective": {},
        "unmodified": {},
    }
    for item in goal.values:
        variants[item.variant][item.code] = {
            "amount": _number(item.amount),
            "unit": item.unit,
        }
    return {
        "source": goal.source,
        "date": goal.local_date.isoformat(),
        "effective": variants["effective"],
        "unmodified": variants["unmodified"],
        "activity_energy_kcal": _number(goal.activity_energy_kcal),
        "consume_activity_energy": goal.consume_activity_energy,
    }


def serialize_sync_run(run: SyncRun | None) -> dict[str, Any]:
    if run is None:
        return {"status": "never_run"}
    return {
        "id": str(run.id),
        "source": run.source,
        "status": run.status,
        "range_start": run.range_start.isoformat(),
        "range_end": run.range_end.isoformat(),
        "started_at": run.started_at.isoformat(),
        "finished_at": run.finished_at.isoformat() if run.finished_at else None,
        "items_seen": run.items_seen,
        "items_upserted": run.items_upserted,
        "items_deleted": run.items_deleted,
        "goals_seen": run.goals_seen,
        "goals_upserted": run.goals_upserted,
        "error_message": run.error_message,
    }
