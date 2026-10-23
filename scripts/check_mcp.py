"""Verify the authenticated, read-only NutriOptimize MCP surface."""

import asyncio
import os
from pathlib import Path

import httpx
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

EXPECTED_TOOLS = {
    "get_nutrition_day",
    "get_nutrition_range",
    "get_sync_status",
}


async def check_mcp() -> None:
    """Connect, verify the tool allowlist, and execute one harmless read."""
    endpoint = os.getenv("MCP_TEST_URL", "http://api:8000/mcp/")
    test_day = os.getenv("MCP_TEST_DAY", "").strip()
    token_file = os.getenv("API_BEARER_TOKEN_FILE", "/run/secrets/api_bearer_token")
    token = (
        await asyncio.to_thread(Path(token_file).read_text, encoding="utf-8")
    ).strip()

    # Supplying the header through an in-memory client keeps the bearer token out
    # of command arguments, URLs and test output.
    async with httpx.AsyncClient(
        headers={"Authorization": f"Bearer {token}"}
    ) as http_client:
        async with streamable_http_client(endpoint, http_client=http_client) as (
            read_stream,
            write_stream,
        ):
            async with ClientSession(read_stream, write_stream) as session:
                await session.initialize()
                listed = await session.list_tools()
                tool_names = {tool.name for tool in listed.tools}
                if tool_names != EXPECTED_TOOLS:
                    raise RuntimeError(
                        "Unexpected MCP tools: "
                        f"expected={sorted(EXPECTED_TOOLS)} actual={sorted(tool_names)}"
                    )

                result = await session.call_tool("get_sync_status", {})
                if result.is_error:
                    raise RuntimeError("get_sync_status returned an MCP tool error")

                if test_day:
                    day_result = await session.call_tool(
                        "get_nutrition_day", {"day": test_day}
                    )
                    if day_result.is_error:
                        raise RuntimeError(
                            "get_nutrition_day returned an MCP tool error"
                        )

    print(f"MCP check passed: {', '.join(sorted(tool_names))}")


if __name__ == "__main__":
    asyncio.run(check_mcp())
