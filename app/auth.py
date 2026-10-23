import asyncio
import hmac
import logging
from collections.abc import Sequence
from typing import Any

import jwt
from jwt import PyJWKClient
from mcp.server.auth.provider import AccessToken
from starlette.responses import JSONResponse

logger = logging.getLogger(__name__)


class BearerAuthMiddleware:
    """Protect selected HTTP route trees without buffering streaming responses."""

    def __init__(self, app, token: str, protected_paths: Sequence[str]):
        self.app = app
        self.token = token
        self.protected_paths = tuple(path.rstrip("/") for path in protected_paths)

    def _is_protected(self, path: str) -> bool:
        return any(
            path == prefix or path.startswith(f"{prefix}/")
            for prefix in self.protected_paths
        )

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        if not self._is_protected(scope.get("path", "")):
            await self.app(scope, receive, send)
            return

        headers = {key.lower(): value for key, value in scope.get("headers", [])}
        provided = headers.get(b"authorization", b"").decode("latin-1")
        expected = f"Bearer {self.token}"
        if not hmac.compare_digest(provided, expected):
            response = JSONResponse(
                {"detail": "Missing or invalid bearer token"},
                status_code=401,
                headers={"WWW-Authenticate": "Bearer"},
            )
            await response(scope, receive, send)
            return

        await self.app(scope, receive, send)


class OIDCJWTVerifier:
    """Verify OAuth access tokens against an OIDC provider's public JWKS.

    The identity provider signs tokens; NutriOptimize only downloads public
    signing keys and validates the resulting JWT. No OAuth client secret is
    needed or stored by this resource server.
    """

    def __init__(
        self,
        *,
        issuer: str,
        audience: str,
        jwks_url: str,
        resource_url: str,
        allowed_subjects: set[str] | None = None,
        algorithm: str = "RS256",
    ):
        self.issuer = issuer
        self.audience = audience
        self.resource_url = resource_url
        self.allowed_subjects = allowed_subjects or set()
        self.algorithm = algorithm
        self._jwks_client = PyJWKClient(
            jwks_url,
            cache_keys=True,
            cache_jwk_set=True,
            lifespan=300,
            timeout=5,
        )

    def _decode(self, token: str) -> dict[str, Any]:
        signing_key = self._jwks_client.get_signing_key_from_jwt(token)
        return jwt.decode(
            token,
            signing_key.key,
            algorithms=[self.algorithm],
            audience=self.audience,
            issuer=self.issuer,
            options={"require": ["exp", "iss", "aud", "sub"]},
        )

    @staticmethod
    def _scopes_from_claims(claims: dict[str, Any]) -> list[str]:
        scopes: set[str] = set()
        raw_scope = claims.get("scope", "")
        if isinstance(raw_scope, str):
            scopes.update(raw_scope.split())

        # Auth0 can optionally place API permissions in a list claim. Supporting
        # both forms keeps authorization explicit without weakening validation.
        permissions = claims.get("permissions", [])
        if isinstance(permissions, list):
            scopes.update(item for item in permissions if isinstance(item, str))
        return sorted(scopes)

    async def verify_token(self, token: str) -> AccessToken | None:
        try:
            # PyJWKClient performs blocking HTTPS I/O when a signing key is not
            # cached, so move it off the ASGI event loop.
            claims = await asyncio.to_thread(self._decode, token)
            subject = claims.get("sub")
            client_id = claims.get("azp") or claims.get("client_id") or subject
            expires_at = claims.get("exp")
            if not isinstance(subject, str) or not subject.strip():
                logger.warning("OAuth token rejected: missing valid subject")
                return None
            if not isinstance(client_id, str):
                logger.warning("OAuth token rejected: missing valid client identifier")
                return None
            if not isinstance(expires_at, int):
                logger.warning("OAuth token rejected: missing valid expiration")
                return None
            if self.allowed_subjects and subject not in self.allowed_subjects:
                logger.warning("OAuth token rejected: subject is not allowlisted")
                return None

            scopes = self._scopes_from_claims(claims)
            logger.info(
                "OAuth token verified: required resource matched; scopes=%s",
                " ".join(scopes) if scopes else "(none)",
            )

            # Keep only the issuer claim in request context. Names and email
            # addresses are unnecessary for V1 and would widen data exposure.
            return AccessToken(
                token=token,
                client_id=client_id,
                scopes=scopes,
                expires_at=expires_at,
                resource=self.resource_url,
                subject=subject,
                claims={"iss": claims["iss"]},
            )
        except Exception as error:
            # Authentication must fail closed. Token contents and exception
            # messages are deliberately not logged because they can hold PII.
            # The exception class is safe and is enough to distinguish common
            # issuer, audience, expiry and JWKS failures during deployment.
            logger.warning(
                "OAuth token verification failed: type=%s",
                type(error).__name__,
            )
            return None
