from datetime import date

from mcp.server import MCPServer
from mcp.server.auth.middleware.auth_context import get_access_token
from mcp.server.auth.settings import AuthSettings
from mcp.server.transport_security import TransportSecuritySettings
from mcp.types import ToolAnnotations
from pydantic import AnyHttpUrl, BaseModel, ConfigDict, Field, TypeAdapter

from app.auth import OIDCJWTVerifier
from app.config import get_settings
from app.db import session_factory
from app.query_service import get_day, get_range
from app.query_service import get_sync_status as query_sync_status

settings = get_settings()
settings.validate_oauth_configuration()

READ_ONLY_TOOL = ToolAnnotations(
    read_only_hint=True,
    destructive_hint=False,
    idempotent_hint=True,
    open_world_hint=False,
)


def _tool_meta(*, profile: bool = False) -> dict[str, object] | None:
    """Advertise each tool's OAuth requirement to OpenAI MCP clients.

    The MCP Python SDK currently exposes vendor extension fields through
    ``_meta``. ChatGPT documents ``_meta.securitySchemes`` as the compatibility
    mirror for clients that cannot yet read a top-level ``securitySchemes``
    field. Authentication is still enforced by the server-level token verifier;
    this metadata only tells the client which OAuth scope it must request.
    """
    meta: dict[str, object] = {}
    if settings.mcp_auth_mode == "oauth":
        meta["securitySchemes"] = [
            {"type": "oauth2", "scopes": settings.oauth_required_scopes}
        ]
    if profile:
        meta["openai/profile"] = True
    return meta or None


class AuthenticatedProfile(BaseModel):
    """Minimal stable identity used to distinguish OAuth connections."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(
        min_length=1,
        pattern=r"\S",
        description=(
            "Opaque identity-provider subject. It remains stable across token "
            "refreshes and reconnects and is never derived from an email address."
        ),
    )


def _http_url(value: str) -> AnyHttpUrl:
    return TypeAdapter(AnyHttpUrl).validate_python(value)


def _oauth_components() -> tuple[AuthSettings | None, OIDCJWTVerifier | None]:
    if settings.mcp_auth_mode != "oauth":
        return None, None

    verifier = OIDCJWTVerifier(
        issuer=settings.mcp_oauth_issuer,
        audience=settings.mcp_oauth_audience,
        jwks_url=settings.mcp_oauth_jwks_url,
        resource_url=settings.mcp_oauth_resource_url,
        allowed_subjects=settings.oauth_allowed_subjects,
    )
    auth = AuthSettings(
        issuer_url=_http_url(settings.mcp_oauth_issuer),
        resource_server_url=_http_url(settings.mcp_oauth_resource_url),
        required_scopes=settings.oauth_required_scopes,
        validate_token_resource=True,
    )
    return auth, verifier


oauth_settings, token_verifier = _oauth_components()

mcp = MCPServer(
    "NutriOptimize",
    instructions=(
        "Read-only access to the user's synchronized nutrition diary. "
        "Use date ranges sparingly and explain that missing nutrients are unknown, not zero. "
        "When targets are present, call effective.energy_kcal the YAZIO daily calorie "
        "target, not a measured total energy expenditure. Unmodified targets are YAZIO's "
        "calculation before manual overrides; keep activity energy separate."
    ),
    auth=oauth_settings,
    token_verifier=token_verifier,
)


if settings.mcp_auth_mode == "oauth":

    @mcp.tool(
        annotations=READ_ONLY_TOOL,
        meta=_tool_meta(profile=True),
        structured_output=True,
    )
    async def get_profile() -> AuthenticatedProfile:
        """Return the stable profile represented by this request's OAuth token."""
        access_token = get_access_token()
        if access_token is None or not access_token.subject:
            # The server-level OAuth middleware normally rejects this earlier.
            # Keeping the handler fail-closed prevents a future routing change
            # from inventing or accepting an unauthenticated profile.
            raise RuntimeError("Authenticated profile identity is unavailable")
        return AuthenticatedProfile(id=access_token.subject)


@mcp.tool(annotations=READ_ONLY_TOOL, meta=_tool_meta())
async def get_sync_status():
    """Return the most recent diary synchronization result."""
    return await query_sync_status(session_factory)


@mcp.tool(annotations=READ_ONLY_TOOL, meta=_tool_meta())
async def get_nutrition_day(day: date):
    """Return food entries and nutrient totals for one local calendar day (YYYY-MM-DD)."""
    return await get_day(session_factory, day)


@mcp.tool(annotations=READ_ONLY_TOOL, meta=_tool_meta())
async def get_nutrition_range(start_date: date, end_date: date):
    """Return diary data for an inclusive local-date range of at most 93 days."""
    return await get_range(session_factory, start_date, end_date)


transport_security = TransportSecuritySettings(
    allowed_hosts=settings.allowed_hosts,
    allowed_origins=settings.allowed_origins,
)
mcp_app = mcp.streamable_http_app(
    # Mount the generated ASGI app at the FastAPI root. For a resource ending in
    # /mcp/, RFC 9728 discovery lives at
    # /.well-known/oauth-protected-resource/mcp/ rather than below /mcp/.
    streamable_http_path="/mcp/",
    transport_security=transport_security,
    stateless_http=True,
    json_response=True,
)
