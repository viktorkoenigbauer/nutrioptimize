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
# HTTPX's INFO log includes full request URLs. Product and recipe identifiers
# are health-adjacent metadata, so routine logs keep only aggregate results.
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)


async def main() -> None:
    settings = get_settings()
    today = datetime.now(ZoneInfo(settings.app_timezone)).date()
    start_date = today - timedelta(days=settings.sync_lookback_days - 1)
    source = build_source(settings)
    try:
        try:
            await run_sync(session_factory, source, start_date, today)
        except Exception as error:  # noqa: BLE001 - keep sensitive details off stdout
            logger.error("One-shot sync stopped: type=%s", type(error).__name__)
            raise SystemExit(1) from None
    finally:
        close_source = getattr(source, "aclose", None)
        if close_source is not None:
            await close_source()
        await close_database()


if __name__ == "__main__":
    asyncio.run(main())
