import asyncio
import logging
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from app.config import get_settings
from app.db import close_database, session_factory
from app.source_factory import build_source
from app.sync_service import run_sync

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s"
)
# Keep upstream URLs and product/recipe identifiers out of routine logs.
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)


async def main() -> None:
    settings = get_settings()
    source = build_source(settings)
    try:
        while True:
            today = datetime.now(ZoneInfo(settings.app_timezone)).date()
            start_date = today - timedelta(days=settings.sync_lookback_days - 1)
            try:
                await run_sync(session_factory, source, start_date, today)
            except Exception:  # noqa: BLE001 - one failed cycle must not stop future retries
                logger.warning(
                    "The next scheduled attempt will retry the same date window"
                )
            await asyncio.sleep(settings.sync_interval_seconds)
    finally:
        close_source = getattr(source, "aclose", None)
        if close_source is not None:
            await close_source()
        await close_database()


if __name__ == "__main__":
    asyncio.run(main())
