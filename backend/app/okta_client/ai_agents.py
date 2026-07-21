"""Wrappers for the Workload Principals Management API (/workload-principals/api/v1).

Base path, scopes, and field names here come from Okta's published API shape.
The one explicitly UNCONFIRMED piece is the owner field shape on the agent
object (see _extract_owners) — flagged in README "Verify-live checklist".
"""

from app.okta_client.base import OktaClient
from app.okta_client.models import AgentDTO, ConnectionDTO, DelegationLinkDTO, ProviderDTO

BASE = "/workload-principals/api/v1"


def _extract_owners(raw: dict) -> tuple[list[str], str | None]:
    """Best-effort parse of owner info. Tries the shapes most consistent with
    Okta's general owner-list convention (a list of {type, id} refs under
    `owners`). If the live tenant's shape differs, this returns ([], None)
    rather than raising — the owner edge is simply omitted for that agent,
    the rest of the graph still renders. Confirm and tighten during Phase 3
    of the build (see plan)."""
    owners = raw.get("owners") or raw.get("_embedded", {}).get("owners") or []
    user_ids: list[str] = []
    group_id: str | None = None
    for owner in owners:
        if not isinstance(owner, dict):
            continue
        owner_type = (owner.get("type") or "").upper()
        owner_id = owner.get("id") or owner.get("value")
        if not owner_id:
            continue
        if owner_type == "GROUP":
            group_id = owner_id
        else:
            user_ids.append(owner_id)
    return user_ids, group_id


def _extract_provider_id(raw: dict) -> str | None:
    """Best-effort: an imported agent links to its provider via `_links.providers`
    per the reference material, but the exact href-vs-inline-id shape wasn't
    confirmed live. Tries a direct id field first, then the last path segment
    of a providers link href."""
    if raw.get("providerId"):
        return raw["providerId"]
    providers_link = raw.get("_links", {}).get("providers")
    if isinstance(providers_link, dict):
        href = providers_link.get("href", "")
        if href:
            return href.rstrip("/").rsplit("/", 1)[-1] or None
    return None


def _parse_agent(raw: dict) -> AgentDTO:
    profile = raw.get("profile", {})
    owner_user_ids, owner_group_id = _extract_owners(raw)
    return AgentDTO(
        id=raw["id"],
        name=profile.get("name", raw["id"]),
        description=profile.get("description"),
        status=raw.get("status", "UNKNOWN"),
        platform=raw.get("platform"),
        external_id=raw.get("externalId"),
        linked_app_id=raw.get("appId") or raw.get("linkedAppId"),
        owner_user_ids=owner_user_ids,
        owner_group_id=owner_group_id,
        orn=raw.get("orn"),
        provider_id=_extract_provider_id(raw),
        raw=raw,
    )


def _parse_connection(raw: dict, agent_id: str) -> ConnectionDTO:
    connection_type = raw.get("connectionType", "UNKNOWN")
    resource = raw.get("resource") or {}
    auth_server = raw.get("authorizationServer") or {}

    resource_type = resource.get("resourceType") if connection_type == "STS_ACCESS_TOKEN" else None
    resource_id = (
        resource.get("appInstanceId")
        or resource.get("apiServerId")
        or resource.get("mcpServerId")
    )

    return ConnectionDTO(
        id=raw["id"],
        agent_id=agent_id,
        connection_type=connection_type,
        status=raw.get("status", "UNKNOWN"),
        resource_type=resource_type,
        resource_id=resource_id,
        resource_indicator=raw.get("resourceIndicator") or resource.get("resourceIndicator"),
        scope_condition=raw.get("scopeCondition"),
        scopes=raw.get("scopes", []),
        authorization_server_id=auth_server.get("id"),
        raw=raw,
    )


def _parse_delegation(raw: dict) -> DelegationLinkDTO:
    from_ = raw.get("from", {})
    to_ = raw.get("to", {})
    return DelegationLinkDTO(
        id=raw["id"],
        from_client_orn=from_.get("clientOrn", ""),
        from_token_type=from_.get("tokenType"),
        to_authorization_server_orn=to_.get("authorizationServerOrn", ""),
        to_resource_orn=to_.get("resourceOrn", ""),
        raw=raw,
    )


def _parse_provider(raw: dict) -> ProviderDTO:
    return ProviderDTO(
        id=raw["id"],
        source_name=raw.get("sourceName", raw["id"]),
        source_orn=raw.get("sourceOrn"),
        raw=raw,
    )


async def list_agents(client: OktaClient) -> list[AgentDTO]:
    agents = []
    async for raw in client.paginate(f"{BASE}/ai-agents"):
        agents.append(_parse_agent(raw))
    return agents


async def get_agent(client: OktaClient, agent_id: str) -> AgentDTO:
    raw = await client.get_json(f"{BASE}/ai-agents/{agent_id}")
    return _parse_agent(raw)


async def list_connections(client: OktaClient, agent_id: str) -> list[ConnectionDTO]:
    connections = []
    async for raw in client.paginate(f"{BASE}/ai-agents/{agent_id}/connections"):
        connections.append(_parse_connection(raw, agent_id))
    return connections


async def list_jwks(client: OktaClient, agent_id: str) -> list[dict]:
    """Raw JWK metadata for the detail panel only — never rendered as graph nodes."""
    return await client.get_json(f"{BASE}/ai-agents/{agent_id}/credentials/jwks")


async def list_delegation_links_to(client: OktaClient, agent_orn: str) -> list[DelegationLinkDTO]:
    """Delegation links whose `to.resourceOrn` is this agent. The API rejects
    filtering by `from.resourceOrn`, so finding what an agent delegates TO
    requires sweeping this call across every agent and unioning results
    where from.clientOrn is itself an agent ORN (done by the caller)."""
    # httpx URL-encodes param values itself; do not pre-quote here.
    filter_query = f'to.resourceOrn eq "{agent_orn}"'
    links = []
    async for raw in client.paginate(f"{BASE}/delegation-links", params={"filter": filter_query}):
        links.append(_parse_delegation(raw))
    return links


async def list_ai_agent_providers(client: OktaClient) -> list[ProviderDTO]:
    providers = []
    async for raw in client.paginate(f"{BASE}/ai-agent-providers"):
        providers.append(_parse_provider(raw))
    return providers
