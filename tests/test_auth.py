import time
import unittest
from unittest.mock import Mock

import jwt
from cryptography.hazmat.primitives.asymmetric import rsa

from app.auth import BearerAuthMiddleware, OIDCJWTVerifier


class BearerAuthMiddlewareTests(unittest.TestCase):
    def test_route_matching_does_not_accept_similar_prefixes(self):
        middleware = BearerAuthMiddleware(
            app=Mock(), token="secret", protected_paths=["/v1", "/mcp"]
        )

        self.assertTrue(middleware._is_protected("/v1"))
        self.assertTrue(middleware._is_protected("/v1/sync/status"))
        self.assertTrue(middleware._is_protected("/mcp/"))
        self.assertFalse(middleware._is_protected("/v10"))
        self.assertFalse(middleware._is_protected("/mcp-public"))
        self.assertFalse(middleware._is_protected("/health/live"))


class OIDCJWTVerifierTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.private_key = rsa.generate_private_key(
            public_exponent=65537, key_size=2048
        )
        self.issuer = "https://identity.example.test/"
        self.audience = "https://api.example.test/mcp/"
        self.verifier = OIDCJWTVerifier(
            issuer=self.issuer,
            audience=self.audience,
            jwks_url="https://identity.example.test/.well-known/jwks.json",
            resource_url=self.audience,
        )
        signing_key = Mock()
        signing_key.key = self.private_key.public_key()
        self.verifier._jwks_client.get_signing_key_from_jwt = Mock(
            return_value=signing_key
        )

    def _token(self, **overrides):
        now = int(time.time())
        claims = {
            "iss": self.issuer,
            "aud": self.audience,
            "sub": "user-123",
            "azp": "chatgpt-client",
            "scope": "openid nutrition:read",
            "iat": now,
            "exp": now + 300,
        }
        claims.update(overrides)
        return jwt.encode(
            claims,
            self.private_key,
            algorithm="RS256",
            headers={"kid": "test-key"},
        )

    async def test_valid_token_becomes_scoped_mcp_access_token(self):
        access_token = await self.verifier.verify_token(self._token())

        self.assertIsNotNone(access_token)
        self.assertEqual(access_token.client_id, "chatgpt-client")
        self.assertEqual(access_token.subject, "user-123")
        self.assertEqual(access_token.resource, self.audience)
        self.assertIn("nutrition:read", access_token.scopes)
        self.assertEqual(access_token.claims, {"iss": self.issuer})

    async def test_wrong_audience_fails_closed(self):
        access_token = await self.verifier.verify_token(
            self._token(aud="https://attacker.example/mcp/")
        )

        self.assertIsNone(access_token)

    async def test_permissions_claim_is_also_treated_as_scope(self):
        access_token = await self.verifier.verify_token(
            self._token(scope="openid", permissions=["nutrition:read"])
        )

        self.assertIn("nutrition:read", access_token.scopes)

    async def test_subject_allowlist_rejects_other_tenant_users(self):
        self.verifier.allowed_subjects = {"user-allowed"}

        access_token = await self.verifier.verify_token(self._token(sub="user-other"))

        self.assertIsNone(access_token)

    async def test_missing_subject_fails_closed(self):
        access_token = await self.verifier.verify_token(self._token(sub=None))

        self.assertIsNone(access_token)


if __name__ == "__main__":
    unittest.main()
