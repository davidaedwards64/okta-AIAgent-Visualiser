"""MCP Server by-id lookup.

UNCONFIRMED against a live tenant: exact base path and scope name (see README
"Verify-live checklist" — item 2). Guesses `/api/v1/mcp-servers/{id}`,
mirroring the resource-servers guess, and fails soft rather than crashing the
graph fetch if wrong. Update this path once confirmed live.
"""

from app.errors import OktaApiError
from app.okta_client.base import OktaClient
from app.okta_client.models import DirectoryObjectDTO

GUESSED_BASE = "/api/v1/mcp-servers"


async def get_mcp_server(client: OktaClient, mcp_server_id: str) -> DirectoryObjectDTO | None:
    try:
        raw = await client.get_json(f"{GUESSED_BASE}/{mcp_server_id}")
    except OktaApiError:
        return None
    return DirectoryObjectDTO(
        id=raw.get("id", mcp_server_id),
        label=raw.get("name", mcp_server_id),
        status=raw.get("status"),
        sub_label=raw.get("baseUrl") or raw.get("url"),
        raw=raw,
    )
