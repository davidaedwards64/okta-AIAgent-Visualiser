import asyncio
import json
from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.auth.dependencies import ensure_valid_token
from app.errors import OktaApiError
from app.graph.assemble import assemble_graph
from app.graph.contract import GraphResponse
from app.okta_client import ai_agents, directory
from app.okta_client.base import OktaClient
from app.okta_client.models import (
    AgentDTO,
    ConnectionDTO,
    DelegationLinkDTO,
    DirectoryObjectDTO,
    PolicyRuleGrantDTO,
    ProviderDTO,
)
from app.session.models import SessionData

router = APIRouter(prefix="/api", tags=["graph"])

CONCURRENCY = 6
MAX_GROUP_MEMBERS = 50  # per group, to keep a single huge directory group from swamping the graph


class GroupMemberSummary(BaseModel):
    id: str
    label: str
    status: str | None = None
    sub_label: str | None = None


class GroupMembersResponse(BaseModel):
    group_id: str
    members: list[GroupMemberSummary]
    total_count: int  # may exceed len(members) if capped by MAX_GROUP_MEMBERS


@dataclass
class GraphFetchContext:
    """Everything assemble_graph needs, fetched and resolved but not yet
    assembled into a GraphResponse. Shared by the graph pipeline below and by
    the risk-report pipeline (app/risk/router.py), so both build on the exact
    same fetch/resolve logic instead of duplicating it."""

    agents: list[AgentDTO]
    connections_by_agent: dict[str, list[ConnectionDTO]]
    delegations_by_agent: dict[str, list[DelegationLinkDTO]]
    agent_orn_to_id: dict[str, str]
    users: dict[str, DirectoryObjectDTO]
    groups: dict[str, DirectoryObjectDTO]
    apps: dict[str, DirectoryObjectDTO]
    auth_servers: dict[str, DirectoryObjectDTO]
    providers: dict[str, ProviderDTO]
    app_groups: dict[str, list[str]]
    auth_server_policy_grants: dict[str, dict[str, list[PolicyRuleGrantDTO]]]
    warnings: list[str]


async def _fetch_graph_context(session: SessionData) -> AsyncIterator[dict]:
    """The fetch/resolve half of the graph-build pipeline (everything
    assemble_graph needs as input), instrumented with progress checkpoints.
    An async generator like _build_graph_with_progress itself: yields
    progress events, then a final `{"stage": "context", "context": ...}`
    event carrying a GraphFetchContext — callers that don't care about
    progress (the risk-report endpoint) can just take that last event."""
    client = OktaClient(session.org_domain, session.access_token)
    warnings: list[str] = []

    yield {"stage": "agents", "message": "Fetching AI Agents..."}
    agents = await ai_agents.list_agents(client)
    yield {"stage": "agents", "message": f"Fetched {len(agents)} agent(s)"}

    sem = asyncio.Semaphore(CONCURRENCY)

    async def fetch_agent_children(
        agent: AgentDTO,
    ) -> tuple[list[ConnectionDTO], list[DelegationLinkDTO], list[str], str | None]:
        async with sem:
            connections = await ai_agents.list_connections(client, agent.id)
            delegations: list[DelegationLinkDTO] = []
            owner_user_ids: list[str] = []
            owner_group_id: str | None = None
            if agent.orn:
                delegations = await ai_agents.list_delegation_links_to(client, agent.orn)
                owner_user_ids, owner_group_id = await ai_agents.get_agent_owners(client, agent.orn)
            else:
                warnings.append(f"agent {agent.id}: no ORN available, skipped delegation and owners lookup")
            return connections, delegations, owner_user_ids, owner_group_id

    yield {"stage": "connections", "message": "Fetching connections & delegation links..."}
    children = await asyncio.gather(*(fetch_agent_children(a) for a in agents))
    connections_by_agent: dict[str, list[ConnectionDTO]] = {}
    delegations_by_agent: dict[str, list[DelegationLinkDTO]] = {}
    for i, (agent, (connections, delegations, owner_user_ids, owner_group_id)) in enumerate(zip(agents, children)):
        connections_by_agent[agent.id] = connections
        delegations_by_agent[agent.id] = delegations
        # The dedicated owners sub-resource is the authoritative source when
        # it returns anything; fall back to whatever _parse_agent already
        # found embedded on the agent object itself (normally nothing — see
        # ai_agents._extract_owners) rather than clobbering it with an empty
        # result from a wrong/unavailable endpoint guess.
        if owner_user_ids or owner_group_id:
            agents[i] = agent.model_copy(update={"owner_user_ids": owner_user_ids, "owner_group_id": owner_group_id})

    agent_orn_to_id = {agent.orn: agent.id for agent in agents if agent.orn}

    # Collect the distinct set of referenced directory-object IDs. Never call
    # the org-wide list endpoints — only these targeted by-id lookups.
    user_ids: set[str] = set()
    group_ids: set[str] = set()
    app_ids: set[str] = set()
    auth_server_ids: set[str] = set()
    provider_ids: set[str] = set()

    for agent in agents:
        user_ids.update(agent.owner_user_ids)
        if agent.owner_group_id:
            group_ids.add(agent.owner_group_id)
        if agent.linked_app_id:
            app_ids.add(agent.linked_app_id)
        if agent.provider_id:
            provider_ids.add(agent.provider_id)

    for connections in connections_by_agent.values():
        for connection in connections:
            if connection.connection_type == "IDENTITY_ASSERTION_CUSTOM_AS" and connection.authorization_server_id:
                auth_server_ids.add(connection.authorization_server_id)
            elif (
                connection.connection_type == "STS_ACCESS_TOKEN"
                and connection.resource_type == "APP_INSTANCE"
                and connection.resource_id
            ):
                app_ids.add(connection.resource_id)

    # Fetched ahead of the directory-resolution batch below (rather than
    # alongside it) so a provider's linked_app_id — the underlying
    # Application whose admin-assigned label replaces the provider's generic
    # sourceName — can be folded into app_ids before that batch runs.
    if provider_ids:
        yield {"stage": "providers", "message": "Resolving import providers..."}
    providers_list = await ai_agents.list_ai_agent_providers(client) if provider_ids else []
    providers_map: dict[str, ProviderDTO] = {p.id: p for p in providers_list if p.id in provider_ids}
    for provider in providers_map.values():
        if provider.linked_app_id:
            app_ids.add(provider.linked_app_id)

    async def fetch_app_groups(app_id: str) -> tuple[str, list[str]]:
        async with sem:
            try:
                return app_id, await directory.list_app_group_ids(client, app_id)
            except OktaApiError as exc:
                warnings.append(f"application {app_id}: could not fetch assigned groups ({exc})")
                return app_id, []

    async def fetch_as_policy_grants(auth_server_id: str) -> tuple[str, dict[str, list[PolicyRuleGrantDTO]]]:
        async with sem:
            try:
                return auth_server_id, await directory.list_authorization_server_policy_grants(
                    client, auth_server_id
                )
            except OktaApiError as exc:
                warnings.append(f"authorizationServer {auth_server_id}: could not fetch policy groups ({exc})")
                return auth_server_id, {}

    yield {"stage": "groups", "message": "Resolving app-assigned & policy-referenced groups..."}
    # Widen group_ids with groups assigned to referenced apps and groups
    # referenced by Access Policy Rules on referenced custom Authorization
    # Servers, so they get resolved in the same batch below.
    app_group_results, as_policy_grant_results = await asyncio.gather(
        asyncio.gather(*(fetch_app_groups(id_) for id_ in app_ids)),
        asyncio.gather(*(fetch_as_policy_grants(id_) for id_ in auth_server_ids)),
    )
    app_groups = dict(app_group_results)
    auth_server_policy_grants = dict(as_policy_grant_results)
    for ids in app_groups.values():
        group_ids.update(ids)
    for grants in auth_server_policy_grants.values():
        group_ids.update(grants.keys())

    async def resolve_all(ids: set[str], fetch_one) -> dict[str, DirectoryObjectDTO]:
        async def bounded(id_: str):
            async with sem:
                return id_, await fetch_one(id_)

        results = await asyncio.gather(*(bounded(id_) for id_ in ids))
        return {id_: obj for id_, obj in results if obj is not None}

    yield {"stage": "directory", "message": "Resolving users, groups, apps & authorization servers..."}
    users, groups, apps, auth_servers_map = await asyncio.gather(
        resolve_all(user_ids, lambda id_: directory.get_user(client, id_)),
        resolve_all(group_ids, lambda id_: directory.get_group(client, id_)),
        resolve_all(app_ids, lambda id_: directory.get_app(client, id_)),
        resolve_all(auth_server_ids, lambda id_: directory.get_authorization_server(client, id_)),
    )

    yield {
        "stage": "context",
        "context": GraphFetchContext(
            agents=agents,
            connections_by_agent=connections_by_agent,
            delegations_by_agent=delegations_by_agent,
            agent_orn_to_id=agent_orn_to_id,
            users=users,
            groups=groups,
            apps=apps,
            auth_servers=auth_servers_map,
            providers=providers_map,
            app_groups=app_groups,
            auth_server_policy_grants=auth_server_policy_grants,
            warnings=warnings,
        ),
    }


async def _build_graph_with_progress(session: SessionData) -> AsyncIterator[dict]:
    """Thin wrapper: forwards _fetch_graph_context's progress events, then
    assembles the final GraphResponse from its context — no behavior change
    from before the refactor, same yielded stage sequence for /graph and
    /graph/stream."""
    ctx: GraphFetchContext | None = None
    async for event in _fetch_graph_context(session):
        if event["stage"] == "context":
            ctx = event["context"]
        else:
            yield event
    assert ctx is not None

    yield {"stage": "assembling", "message": "Building graph..."}
    graph = assemble_graph(
        org_domain=session.org_domain,
        generated_at=datetime.now(timezone.utc).isoformat(),
        agents=ctx.agents,
        connections_by_agent=ctx.connections_by_agent,
        delegations_by_agent=ctx.delegations_by_agent,
        agent_orn_to_id=ctx.agent_orn_to_id,
        users=ctx.users,
        groups=ctx.groups,
        apps=ctx.apps,
        auth_servers=ctx.auth_servers,
        providers=ctx.providers,
        app_groups=ctx.app_groups,
        auth_server_policy_grants=ctx.auth_server_policy_grants,
        extra_warnings=ctx.warnings,
    )
    yield {"stage": "done", "graph": graph}


@router.get("/graph", response_model=GraphResponse)
async def get_graph(session: SessionData = Depends(ensure_valid_token)) -> GraphResponse:
    async for event in _build_graph_with_progress(session):
        if event["stage"] == "done":
            return event["graph"]
    raise HTTPException(status_code=500, detail="Graph build did not complete")


@router.get("/graph/stream")
async def stream_graph(session: SessionData = Depends(ensure_valid_token)) -> StreamingResponse:
    """Same pipeline as GET /graph, but forwards each progress checkpoint to
    the browser over Server-Sent Events as it happens, instead of leaving the
    frontend staring at one static "Loading..." message for the whole
    request. Exceptions mid-stream are reported as a final "error" event
    rather than just dropping the connection, so the frontend gets a real
    message instead of a generic network failure."""

    async def event_stream() -> AsyncIterator[str]:
        try:
            async for event in _build_graph_with_progress(session):
                if event["stage"] == "done":
                    payload = {"stage": "done", "graph": event["graph"].model_dump(mode="json")}
                else:
                    payload = event
                yield f"data: {json.dumps(payload)}\n\n"
        except OktaApiError as exc:
            yield f"data: {json.dumps({'stage': 'error', 'message': str(exc)})}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@router.get("/groups/{group_id}/members", response_model=GroupMembersResponse)
async def get_group_members(
    group_id: str, session: SessionData = Depends(ensure_valid_token)
) -> GroupMembersResponse:
    """On-demand only — never called as part of the main graph fetch. Lets
    the frontend reveal a group's members (global toggle or per-group
    right-click) without paying for every group's membership on every load,
    which for Okta's built-in "Everyone" group means every user in the org."""
    client = OktaClient(session.org_domain, session.access_token)
    try:
        members = await directory.list_group_members(client, group_id)
    except OktaApiError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return GroupMembersResponse(
        group_id=group_id,
        members=[
            GroupMemberSummary(id=m.id, label=m.label, status=m.status, sub_label=m.sub_label)
            for m in members[:MAX_GROUP_MEMBERS]
        ],
        total_count=len(members),
    )
