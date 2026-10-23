from contextlib import asynccontextmanager
from datetime import date

from fastapi import FastAPI, HTTPException
from sqlalchemy import text

from app import __version__
from app.auth import BearerAuthMiddleware
from app.config import get_settings
from app.db import close_database, engine, session_factory
from app.mcp_server import mcp, mcp_app
from app.query_service import get_day, get_range, get_sync_status

settings = get_settings()


@asynccontextmanager
async def lifespan(application: FastAPI):
    async with mcp.session_manager.run():
        yield
    await close_database()


app = FastAPI(
    title="NutriOptimize API",
    version=__version__,
    openapi_url=None,
    docs_url=None,
    redoc_url=None,
    lifespan=lifespan,
)


@app.get("/health/live")
async def live():
    return {"status": "ok"}


@app.get("/health/ready")
async def ready():
    try:
        async with engine.connect() as connection:
            await connection.execute(text("select 1"))
    except Exception as error:
        raise HTTPException(status_code=503, detail="database unavailable") from error
    return {"status": "ready"}


@app.get("/v1/sync/status")
async def sync_status():
    return await get_sync_status(session_factory)


@app.get("/v1/nutrition/days/{day}")
async def nutrition_day(day: date):
    return await get_day(session_factory, day)


@app.get("/v1/nutrition/range")
async def nutrition_range(start_date: date, end_date: date):
    try:
        return await get_range(session_factory, start_date, end_date)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


# The MCP SDK must live at the application root so its OAuth discovery route is
# not accidentally nested below /mcp. Explicit FastAPI routes above still win.
app.mount("/", mcp_app)

static_paths = ["/v1"]
if settings.mcp_auth_mode == "static":
    static_paths.append("/mcp")
app.add_middleware(
    BearerAuthMiddleware,
    token=settings.api_bearer_token,
    protected_paths=static_paths,
)
