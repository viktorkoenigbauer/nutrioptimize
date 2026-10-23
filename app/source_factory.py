from app.config import Settings
from app.sources.base import NutritionSource
from app.sources.fixture import FixtureSource
from app.sources.yazio import YazioSource


def build_source(settings: Settings) -> NutritionSource:
    """Build the configured adapter without leaking its credentials elsewhere."""
    if settings.sync_source == "fixture":
        return FixtureSource(settings.app_timezone)
    if settings.sync_source == "yazio":
        return YazioSource(
            timezone_name=settings.app_timezone,
            email=settings.yazio_email,
            password=settings.yazio_password,
            client_id=settings.yazio_client_id,
            client_secret=settings.yazio_client_secret,
            base_url=settings.yazio_base_url,
            api_version=settings.yazio_api_version,
            user_agent=settings.yazio_user_agent,
            accept_language=settings.yazio_accept_language,
            timeout_seconds=settings.yazio_timeout_seconds,
            max_concurrency=settings.yazio_max_concurrency,
        )
    raise ValueError(f"Unsupported SYNC_SOURCE: {settings.sync_source}")
