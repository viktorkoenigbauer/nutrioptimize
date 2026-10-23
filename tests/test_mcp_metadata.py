import unittest
from unittest.mock import patch

from app import mcp_server


class MCPToolMetadataTests(unittest.TestCase):
    def test_oauth_tools_advertise_required_scope(self):
        with (
            patch.object(mcp_server.settings, "mcp_auth_mode", "oauth"),
            patch.object(
                mcp_server.settings,
                "mcp_oauth_required_scopes",
                "nutrition:read",
            ),
        ):
            self.assertEqual(
                mcp_server._tool_meta(),
                {"securitySchemes": [{"type": "oauth2", "scopes": ["nutrition:read"]}]},
            )

    def test_profile_marker_is_merged_with_oauth_metadata(self):
        with (
            patch.object(mcp_server.settings, "mcp_auth_mode", "oauth"),
            patch.object(
                mcp_server.settings,
                "mcp_oauth_required_scopes",
                "nutrition:read",
            ),
        ):
            meta = mcp_server._tool_meta(profile=True)

        self.assertTrue(meta["openai/profile"])
        self.assertEqual(meta["securitySchemes"][0]["scopes"], ["nutrition:read"])


if __name__ == "__main__":
    unittest.main()
