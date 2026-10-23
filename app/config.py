from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import URL


def _read_secret(path: str) -> str:
    value = Path(path).read_text(encoding="utf-8").strip()
    if not value:
        raise ValueError(f"Secret file is empty: {path}")
    return value


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_timezone: str = "Europe/Vienna"
    public_host: str = "localhost"

    postgres_host: str = "localhost"
    postgres_port: int = 5432
    postgres_db: str = "nutrioptimize"
    postgres_user: str = "nutrioptimize"
    postgres_password_file: str = "secrets/postgres_password.txt"
    api_bearer_token_file: str = "secrets/api_bearer_token.txt"

    sync_source: str = "fixture"
    sync_interval_seconds: int = Field(default=3600, ge=60)
    sync_lookback_days: int = Field(default=7, ge=1, le=90)
    yazio_email_file: str = "/run/secrets/yazio_email"
    yazio_password_file: str = "/run/secrets/yazio_password"
    yazio_client_id_file: str = "/run/secrets/yazio_client_id"
    yazio_client_secret_file: str = "/run/secrets/yazio_client_secret"
    yazio_base_url: str = "https://yzapi.yazio.com"
    yazio_api_version: str = "v22"
    yazio_user_agent: str = (
        "YAZIO/26.30.1 (com.yazio.ios.YAZIO; build:2607271240; iOS 27.0.0) Ktor"
    )
    yazio_accept_language: str = "de-AT,de;q=0.9,en;q=0.8"
    yazio_timeout_seconds: float = Field(default=20.0, ge=1.0, le=120.0)
    yazio_max_concurrency: int = Field(default=4, ge=1, le=10)
    mcp_allowed_origins: str = ""

    # Static mode keeps local development and command-line diagnostics simple.
    # Production ChatGPT connections use OAuth so every access token has an
    # issuer, audience, expiry and explicit read scope.
    mcp_auth_mode: Literal["static", "oauth"] = "static"
    mcp_oauth_issuer: str = ""
    mcp_oauth_audience: str = ""
    mcp_oauth_jwks_url: str = ""
    mcp_oauth_resource_url: str = ""
    mcp_oauth_required_scopes: str = "nutrition:read"
    mcp_oauth_allowed_subjects: str = ""

    @property
    def postgres_password(self) -> str:
        return _read_secret(self.postgres_password_file)

    @property
    def api_bearer_token(self) -> str:
        return _read_secret(self.api_bearer_token_file)

    @property
    def yazio_email(self) -> str:
        return _read_secret(self.yazio_email_file)

    @property
    def yazio_password(self) -> str:
        return _read_secret(self.yazio_password_file)

    @property
    def yazio_client_id(self) -> str:
        return _read_secret(self.yazio_client_id_file)

    @property
    def yazio_client_secret(self) -> str:
        return _read_secret(self.yazio_client_secret_file)

    @property
    def database_url_async(self) -> URL:
        return URL.create(
            "postgresql+asyncpg",
            username=self.postgres_user,
            password=self.postgres_password,
            host=self.postgres_host,
            port=self.postgres_port,
            database=self.postgres_db,
        )

    @property
    def database_url_sync(self) -> URL:
        return URL.create(
            "postgresql+psycopg",
            username=self.postgres_user,
            password=self.postgres_password,
            host=self.postgres_host,
            port=self.postgres_port,
            database=self.postgres_db,
        )

    @property
    def allowed_hosts(self) -> list[str]:
        hosts = ["localhost", "localhost:*", "127.0.0.1", "127.0.0.1:*", "api", "api:*"]
        if self.public_host not in ("localhost", "127.0.0.1"):
            hosts.extend([self.public_host, f"{self.public_host}:*"])
        return hosts

    @property
    def allowed_origins(self) -> list[str]:
        return [
            item.strip() for item in self.mcp_allowed_origins.split(",") if item.strip()
        ]

    @property
    def oauth_required_scopes(self) -> list[str]:
        scopes = [
            item.strip()
            for item in self.mcp_oauth_required_scopes.replace(",", " ").split()
            if item.strip()
        ]
        if not scopes:
            raise ValueError("MCP_OAUTH_REQUIRED_SCOPES must not be empty")
        return scopes

    @property
    def oauth_allowed_subjects(self) -> set[str]:
        return {
            item.strip()
            for item in self.mcp_oauth_allowed_subjects.split(",")
            if item.strip()
        }

    def validate_oauth_configuration(self) -> None:
        """Fail during startup rather than silently running OAuth half-configured."""
        if self.mcp_auth_mode != "oauth":
            return

        required = {
            "MCP_OAUTH_ISSUER": self.mcp_oauth_issuer,
            "MCP_OAUTH_AUDIENCE": self.mcp_oauth_audience,
            "MCP_OAUTH_JWKS_URL": self.mcp_oauth_jwks_url,
            "MCP_OAUTH_RESOURCE_URL": self.mcp_oauth_resource_url,
        }
        missing = [name for name, value in required.items() if not value.strip()]
        if missing:
            raise ValueError(
                "OAuth mode requires these settings: " + ", ".join(missing)
            )

        https_settings = {
            "MCP_OAUTH_ISSUER": self.mcp_oauth_issuer,
            "MCP_OAUTH_JWKS_URL": self.mcp_oauth_jwks_url,
            "MCP_OAUTH_RESOURCE_URL": self.mcp_oauth_resource_url,
        }
        insecure = [
            name
            for name, value in https_settings.items()
            if not value.startswith("https://")
        ]
        if insecure:
            raise ValueError("OAuth mode requires HTTPS URLs: " + ", ".join(insecure))

        if not self.oauth_allowed_subjects:
            raise ValueError(
                "MCP_OAUTH_ALLOWED_SUBJECTS must contain at least one stable OAuth "
                "subject ID. This single-user server must not expose one person's "
                "nutrition diary to every account accepted by the identity provider."
            )

        # Accessing the property also validates that at least one scope exists.
        _ = self.oauth_required_scopes


@lru_cache
def get_settings() -> Settings:
    return Settings()
