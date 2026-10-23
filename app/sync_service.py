import logging
import uuid
from collections.abc import Callable
from datetime import UTC, date, datetime

from app.models import SyncRun
from app.repository import (
    delete_missing_food_entries,
    upsert_daily_goal,
    upsert_food_entry,
)
from app.sources.base import NutritionSource

logger = logging.getLogger(__name__)


async def run_sync(
    session_factory: Callable, source: NutritionSource, start_date: date, end_date: date
) -> SyncRun:
    run_id = uuid.uuid4()
    started_at = datetime.now(UTC)
    async with session_factory() as session:
        run = SyncRun(
            id=run_id,
            source=source.name,
            status="running",
            range_start=start_date,
            range_end=end_date,
            started_at=started_at,
        )
        session.add(run)
        await session.commit()

    try:
        entries = await source.fetch_entries(start_date, end_date)
        goals = await source.fetch_daily_goals(start_date, end_date)
        changed = 0
        deleted = 0
        goals_changed = 0
        async with session_factory() as session:
            for entry in entries:
                changed += int(await upsert_food_entry(session, entry))
            for goal in goals:
                goals_changed += int(await upsert_daily_goal(session, goal))
            if getattr(source, "authoritative_window", False):
                deleted = await delete_missing_food_entries(
                    session,
                    source=source.name,
                    start_date=start_date,
                    end_date=end_date,
                    external_ids={entry.external_id for entry in entries},
                )
            run = await session.get(SyncRun, run_id)
            run.status = "success"
            run.finished_at = datetime.now(UTC)
            run.items_seen = len(entries)
            run.items_upserted = changed
            run.items_deleted = deleted
            run.goals_seen = len(goals)
            run.goals_upserted = goals_changed
            await session.commit()
            await session.refresh(run)
            logger.info(
                "Sync completed: seen=%s upserted=%s deleted=%s goals_seen=%s goals_upserted=%s",
                len(entries),
                changed,
                deleted,
                len(goals),
                goals_changed,
            )
            return run
    except Exception as error:
        # Upstream exceptions may contain URLs, credentials or diary fragments.
        # Record only the exception class; source adapters can add explicitly
        # redacted diagnostics when they have been reviewed for privacy.
        error_type = type(error).__name__
        logger.error("Sync failed: type=%s", error_type)
        async with session_factory() as session:
            run = await session.get(SyncRun, run_id)
            run.status = "failed"
            run.finished_at = datetime.now(UTC)
            run.error_message = f"{error_type}: synchronization failed"
            await session.commit()
        raise
