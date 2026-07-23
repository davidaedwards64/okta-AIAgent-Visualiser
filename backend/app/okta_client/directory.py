"""By-id lookups only — never call the org-wide list endpoints for users/groups.

The graph's scoping strategy (see graph/assemble.py + the plan) fetches agents
first, collects the distinct set of referenced directory object IDs from their
owners/connections/delegations, then resolves each exactly once via these
functions. That is what keeps this fast regardless of total org size.
"""

from app.errors import OktaApiError
from app.okta_client.base import OktaClient
from app.okta_client.models import DirectoryObjectDTO, PolicyRuleGrantDTO


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


async def find_everyone_group(client: OktaClient) -> DirectoryObjectDTO | None:
    """The one deliberate, isolated exception to this module's by-id-only
    rule: a single filtered lookup (not a paginated org-wide sweep) for
    Okta's well-known built-in Everyone group. Used only by the risk-report
    endpoint as an org-user-count proxy (rule 3). UNCONFIRMED against a live
    tenant that `type eq "BUILT_IN"` uniquely and reliably identifies it —
    see README checklist."""
    try:
        groups = await client.get_json("/api/v1/groups", params={"filter": 'type eq "BUILT_IN"', "limit": 1})
    except OktaApiError:
        return None
    if not groups:
        return None
    raw = groups[0]
    profile = raw.get("profile", {})
    return DirectoryObjectDTO(id=raw["id"], label=profile.get("name", "Everyone"), sub_label=profile.get("description"), raw=raw)


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


async def list_app_group_ids(client: OktaClient, app_id: str) -> list[str]:
    """Groups assigned to an app: GET /api/v1/apps/{id}/groups. Raises
    OktaApiError on failure — the caller (graph/router.py) decides how to
    surface that as a warning rather than this silently returning empty."""
    return [raw["id"] async for raw in client.paginate(f"/api/v1/apps/{app_id}/groups")]


async def list_authorization_server_policy_grants(
    client: OktaClient, auth_server_id: str
) -> dict[str, list[PolicyRuleGrantDTO]]:
    """Access Policy Rules on a custom Authorization Server, keyed by the
    groups they grant access to. Sweeps GET .../policies then GET
    .../policies/{id}/rules for each, collecting conditions.people.groups.include
    plus the granted scopes/grant types — so the graph can show *why* a group
    is connected to this Authorization Server, not just that it is. Raises
    OktaApiError on failure — same reasoning as list_app_group_ids.

    `EVERYONE` is a literal sentinel Okta uses in this field to mean "no group
    restriction" (mirrors the "Everyone" pseudo-group in Sign-On Policies) —
    it is not a real, lookup-able group id, so it's filtered out here rather
    than passed on to fail a directory lookup."""
    grants: dict[str, list[PolicyRuleGrantDTO]] = {}
    async for policy in client.paginate(f"/api/v1/authorizationServers/{auth_server_id}/policies"):
        policy_id = policy.get("id")
        if not policy_id:
            continue
        async for rule in client.paginate(
            f"/api/v1/authorizationServers/{auth_server_id}/policies/{policy_id}/rules"
        ):
            conditions = rule.get("conditions", {})
            group_ids = conditions.get("people", {}).get("groups", {}).get("include", [])
            grant = PolicyRuleGrantDTO(
                policy_name=policy.get("name"),
                rule_name=rule.get("name"),
                rule_status=rule.get("status"),
                grant_types=conditions.get("grantTypes", {}).get("include", []),
                scopes=conditions.get("scopes", {}).get("include", []),
                raw={"policy": policy, "rule": rule},
            )
            for group_id in group_ids:
                if group_id == "EVERYONE":
                    continue
                grants.setdefault(group_id, []).append(grant)
    return grants
