"""Wrappers for the Workload Principals Management API (/workload-principals/api/v1).

Base path, scopes, and field names here come from Okta's published API shape.
Owners are the one exception: the Admin Console's AI Agent "Owners" tab is
not part of this API family at all — confirmed live, via the Admin Console's
own Network tab, to be served by the Governance API instead (see
get_agent_owners).
"""

import re
from urllib.parse import unquote

from app.errors import OktaApiError
from app.okta_client.base import OktaClient
from app.okta_client.models import AgentDTO, ConnectionDTO, DelegationLinkDTO, ProviderDTO

BASE = "/workload-principals/api/v1"
GOVERNANCE_BASE = "/governance/api/v1"


def _parse_owner_refs(owners: list) -> tuple[list[str], str | None]:
    """Shared by _extract_owners and get_agent_owners — both assume the same
    Okta owner-ref convention (a list of {type, id} objects), just sourced
    from different places."""
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


def _extract_owners(raw: dict) -> tuple[list[str], str | None]:
    """Best-effort parse of owner info embedded directly on the agent object.
    Confirmed live: the AI Agent object has no `owners` field at all — the
    Admin Console's "Owners" tab (up to 5 users, or a single group) is backed
    by the Governance API instead (see get_agent_owners). Kept as a
    defensive fallback in case a different/future tenant shape does embed it."""
    owners = raw.get("owners") or raw.get("_embedded", {}).get("owners") or []
    return _parse_owner_refs(owners)


def _parse_owner_principals(principals: list) -> tuple[list[str], str | None]:
    """A resource-owners binding's `principals` entries have their real
    directory id only as the last segment of `orn` — the top-level `id`
    field is an internal principal-ref id, not a user/group id — and `type`
    is plural ("users"/"groups")."""
    user_ids: list[str] = []
    group_id: str | None = None
    for principal in principals:
        principal_id = (principal.get("orn") or "").rsplit(":", 1)[-1]
        if not principal_id:
            continue
        if (principal.get("type") or "").rstrip("s").upper() == "GROUP":
            group_id = principal_id
        else:
            user_ids.append(principal_id)
    return user_ids, group_id


async def get_agent_owners(client: OktaClient, agent_orn: str) -> tuple[list[str], str | None]:
    """The Admin Console's AI Agent "Owners" tab, confirmed live via its own
    Network tab: GET /governance/api/v1/resource-owners, filtered by
    `parentResourceOrn eq "{agent's own orn}"` — a completely different API
    family (Governance, not Workload Principals) keyed off orn rather than
    id."""
    filter_query = f'parentResourceOrn eq "{agent_orn}"'
    user_ids: list[str] = []
    group_id: str | None = None
    try:
        async for binding in client.paginate(f"{GOVERNANCE_BASE}/resource-owners", params={"filter": filter_query}):
            binding_user_ids, binding_group_id = _parse_owner_principals(binding.get("principals", []))
            user_ids.extend(binding_user_ids)
            group_id = binding_group_id or group_id
    except OktaApiError:
        return [], None
    return user_ids, group_id


def _extract_provider_id(raw: dict) -> str | None:
    """An imported agent links to its provider via `_links.providers` — confirmed
    live to be a *list* of link objects (e.g. `[{"href": ".../ai-agent-providers/{id}"}]`),
    not a single dict. Tries a direct id field first, then the last path
    segment of the first providers link href."""
    if raw.get("providerId"):
        return raw["providerId"]
    providers_link = raw.get("_links", {}).get("providers")
    href = ""
    if isinstance(providers_link, list) and providers_link:
        href = providers_link[0].get("href", "")
    elif isinstance(providers_link, dict):
        href = providers_link.get("href", "")
    if not href:
        return None
    return href.rstrip("/").rsplit("/", 1)[-1] or None


def _extract_agent_orn(raw: dict) -> str | None:
    """Confirmed live: the AI Agent object has no top-level `orn` field at
    all. Its own ORN is embedded (URL-encoded) in `_links.delegationLinks.href`,
    e.g. `...delegation-links?filter=to.resourceOrn eq "orn:...:ai-agents:{id}"`
    — pull it out of there rather than giving up on delegation lookups."""
    href = raw.get("_links", {}).get("delegationLinks", {}).get("href", "")
    if not href:
        return None
    match = re.search(r'to\.resourceOrn eq "([^"]+)"', unquote(href))
    return match.group(1) if match else None


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
        orn=raw.get("orn") or _extract_agent_orn(raw),
        provider_id=_extract_provider_id(raw),
        raw=raw,
    )


def _extract_authorization_server_id(auth_server: dict) -> str | None:
    """Confirmed live: the connection's `authorizationServer` object has no
    `id` field at all — only issuerUrl/name/orn/_links.self.href. Same
    href-last-segment fallback as _extract_provider_id."""
    if auth_server.get("id"):
        return auth_server["id"]
    href = auth_server.get("_links", {}).get("self", {}).get("href", "")
    if href:
        return href.rstrip("/").rsplit("/", 1)[-1] or None
    return None


def _extract_a2a_target_agent_id(resource: dict) -> str | None:
    """IDENTITY_ASSERTION_A2A_SERVER connections' `resource` has no direct id
    field either — the target agent's id is the last segment of its orn,
    e.g. orn:oktapreview:directory:...:resource-servers:a2a:{agentId}."""
    orn = resource.get("orn", "")
    if ":resource-servers:a2a:" in orn:
        return orn.rsplit(":", 1)[-1] or None
    return None


def _parse_connection(raw: dict, agent_id: str) -> ConnectionDTO:
    connection_type = raw.get("connectionType", "UNKNOWN")
    resource = raw.get("resource") or {}
    auth_server = raw.get("authorizationServer") or {}

    resource_type = resource.get("resourceType") if connection_type == "STS_ACCESS_TOKEN" else None
    resource_id = (
        resource.get("appInstanceId")
        or resource.get("apiServerId")
        or resource.get("mcpServerId")
        or (_extract_a2a_target_agent_id(resource) if connection_type == "IDENTITY_ASSERTION_A2A_SERVER" else None)
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
        authorization_server_id=_extract_authorization_server_id(auth_server),
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


_APP_ID_PATTERN = re.compile(r"(0oa\w+)")


def _extract_linked_app_id(source_orn: str | None) -> str | None:
    """provider.sourceName (e.g. "amazon_aws_sso") is only the OIN catalog
    key shared by every org using that IdP type, not this org's own
    admin-assigned app label (e.g. "AWS IAM Identity Center") — the label
    lives on the underlying Application object that sourceOrn points at.
    The exact orn structure here is UNCONFIRMED, but Okta app instance ids
    reliably start with "0oa" regardless, so match on that prefix rather
    than assuming a fixed segment position."""
    if not source_orn:
        return None
    match = _APP_ID_PATTERN.search(source_orn)
    return match.group(1) if match else None


def _parse_provider(raw: dict) -> ProviderDTO:
    source_orn = raw.get("sourceOrn")
    return ProviderDTO(
        id=raw["id"],
        source_name=raw.get("sourceName", raw["id"]),
        source_orn=source_orn,
        linked_app_id=_extract_linked_app_id(source_orn),
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
