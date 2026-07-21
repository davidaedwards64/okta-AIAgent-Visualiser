"""By-id lookups only — never call the org-wide list endpoints for users/groups.

The graph's scoping strategy (see graph/assemble.py + the plan) fetches agents
first, collects the distinct set of referenced directory object IDs from their
owners/connections/delegations, then resolves each exactly once via these
functions. That is what keeps this fast regardless of total org size.
"""

from app.errors import OktaApiError
from app.okta_client.base import OktaClient
from app.okta_client.models import DirectoryObjectDTO


async def get_user(client: OktaClient, user_id: str) -> DirectoryObjectDTO | None:
    try:
        raw = await client.get_json(f"/api/v1/users/{user_id}")
    except OktaApiError:
        return None
    profile = raw.get("profile", {})
    label = profile.get("displayName") or profile.get("login") or user_id
    return DirectoryObjectDTO(id=raw["id"], label=label, status=raw.get("status"), sub_label=profile.get("email"), raw=raw)


async def get_group(client: OktaClient, group_id: str) -> DirectoryObjectDTO | None:
    try:
        raw = await client.get_json(f"/api/v1/groups/{group_id}")
    except OktaApiError:
        return None
    profile = raw.get("profile", {})
    return DirectoryObjectDTO(id=raw["id"], label=profile.get("name", group_id), sub_label=profile.get("description"), raw=raw)


async def list_group_members(client: OktaClient, group_id: str) -> list[DirectoryObjectDTO]:
    """On-demand only (detail panel), never fetched eagerly for the main graph."""
    members = []
    async for raw in client.paginate(f"/api/v1/groups/{group_id}/users"):
        profile = raw.get("profile", {})
        label = profile.get("displayName") or profile.get("login") or raw["id"]
        members.append(DirectoryObjectDTO(id=raw["id"], label=label, status=raw.get("status"), raw=raw))
    return members


async def get_app(client: OktaClient, app_id: str) -> DirectoryObjectDTO | None:
    try:
        raw = await client.get_json(f"/api/v1/apps/{app_id}")
    except OktaApiError:
        return None
    return DirectoryObjectDTO(
        id=raw["id"],
        label=raw.get("label", app_id),
        status=raw.get("status"),
        sub_label=raw.get("name"),  # OIN catalog key, needed for the "Open in Okta" deep link
        raw=raw,
    )


async def get_authorization_server(client: OktaClient, auth_server_id: str) -> DirectoryObjectDTO | None:
    try:
        raw = await client.get_json(f"/api/v1/authorizationServers/{auth_server_id}")
    except OktaApiError:
        return None
    return DirectoryObjectDTO(
        id=raw["id"], label=raw.get("name", auth_server_id), status=raw.get("status"),
        sub_label=raw.get("issuer"), raw=raw,
    )
