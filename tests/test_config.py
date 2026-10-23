import unittest

from app.config import Settings


class OAuthConfigurationTests(unittest.TestCase):
    def _settings(self, **overrides) -> Settings:
        values = {
            "mcp_auth_mode": "oauth",
            "mcp_oauth_issuer": "https://login.example.test/",
            "mcp_oauth_audience": "https://api.example.test/mcp/",
            "mcp_oauth_jwks_url": "https://login.example.test/.well-known/jwks.json",
            "mcp_oauth_resource_url": "https://api.example.test/mcp/",
            "mcp_oauth_required_scopes": "nutrition:read",
            "mcp_oauth_allowed_subjects": "auth0|user-123",
        }
        values.update(overrides)
        return Settings(_env_file=None, **values)

    def test_complete_single_user_oauth_configuration_is_valid(self):
        self._settings().validate_oauth_configuration()

    def test_oauth_rejects_missing_subject_allowlist(self):
        settings = self._settings(mcp_oauth_allowed_subjects="")

        with self.assertRaisesRegex(ValueError, "MCP_OAUTH_ALLOWED_SUBJECTS"):
            settings.validate_oauth_configuration()

    def test_oauth_rejects_non_https_metadata(self):
        settings = self._settings(
            mcp_oauth_jwks_url="http://login.example.test/.well-known/jwks.json"
        )

        with self.assertRaisesRegex(ValueError, "HTTPS"):
            settings.validate_oauth_configuration()


if __name__ == "__main__":
    unittest.main()
