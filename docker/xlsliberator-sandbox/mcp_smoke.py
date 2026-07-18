#!/opt/xlsliberator-venv/bin/python
"""Fail-closed connectivity smoke for the LibreOffice runtime MCP."""

from __future__ import annotations

import asyncio
import json
import os

from fastmcp import Client

EXPECTED_TOOLS = {
    "create_session",
    "open_document",
    "inspect_document",
    "capture_screenshot",
    "destroy_session",
}


async def main() -> None:
    endpoint = os.environ.get("XLSLIBERATOR_LIBREOFFICE_MCP_ENDPOINT", "").strip()
    if not endpoint:
        raise SystemExit("XLSLIBERATOR_LIBREOFFICE_MCP_ENDPOINT is required")
    async with Client(endpoint) as client:
        tools = await client.list_tools()
    names = {tool.name for tool in tools}
    missing = sorted(EXPECTED_TOOLS - names)
    if missing:
        raise SystemExit(f"LibreOffice MCP is missing required tools: {', '.join(missing)}")
    print(
        json.dumps(
            {
                "status": "PASSED",
                "endpoint": endpoint,
                "tools": sorted(names),
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    asyncio.run(main())
