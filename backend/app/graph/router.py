import asyncio
from datetime import datetime, timezone

from fastapi import APIRouter, Depends

from app.auth.dependencies import ensure_valid_token
from app.graph.assemble import assemble_graph
from app.graph.contract import GraphResponse
from app.okta_client import ai_agents, directory, mcp_servers, resource_servers
from app.okta_client.base import OktaClient
from app.okta_client.models import AgentDTO, ConnectionDTO, DelegationLinkDTO, DirectoryObjectDTO, ProviderDTO
from app.session.models import SessionData

router = APIRouter(prefix="/api", tags=["graph"])

CONCURRENCY = 6


@router.get("/graph", response_model=GraphResponse)
async def get_graph(session: SessionData = Depends(ensure_valid_token)) -> GraphResponse:
    client = OktaClient(session.org_domain, session.access_token)
    warnings: list[str] = []

    agents = await ai_agents.list_agents(client)

    sem = asyncio.Semaphore(CONCURRENCY)

    async def fetch_agent_children(agent: AgentDTO) -> tuple[list[ConnectionDTO], list[DelegationLinkDTO]]:
        async with sem:
            connections = await ai_agents.list_connections(client, agent.id)
            delegations: list[DelegationLinkDTO] = []
            if agent.orn:
                delegations = await ai_agents.list_delegation_links_to(client, agent.orn)
            else:
                warnings.append(f"agent {agent.id}: no ORN available, skipped delegation lookup")
            return connections, delegations

    children = await asyncio.gather(*(fetch_agent_children(a) for a in agents))
    connections_by_agent: dict[str, list[ConnectionDTO]] = {}
    delegations_by_agent: dict[str, list[DelegationLinkDTO]] = {}
    for agent, (connections, delegations) in zip(agents, children):
        connections_by_agent[agent.id] = connections
        delegations_by_agent[agent.id] = delegations

    agent_orn_to_id = {agent.orn: agent.id for agent in agents if agent.orn}

    # Collect the distinct set of referenced directory-object IDs. Never call
    # the org-wide list endpoints — only these targeted by-id lookups.
    user_ids: set[str] = set()
    group_ids: set[str] = set()
    app_ids: set[str] = set()
    auth_server_ids: set[str] = set()
    resource_server_ids: set[str] = set()
    mcp_server_ids: set[str] = set()
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
            elif connection.connection_type == "STS_ACCESS_TOKEN" and connection.resource_id:
                if connection.resource_type == "APP_INSTANCE":
                    app_ids.add(connection.resource_id)
                elif connection.resource_type == "API_SERVER":
                    resource_server_ids.add(connection.resource_id)
                elif connection.resource_type == "MCP_SERVER":
                    mcp_server_ids.add(connection.resource_id)

    async def resolve_all(ids: set[str], fetch_one) -> dict[str, DirectoryObjectDTO]:
        async def bounded(id_: str):
            async with sem:
                return id_, await fetch_one(id_)

        results = await asyncio.gather(*(bounded(id_) for id_ in ids))
        return {id_: obj for id_, obj in results if obj is not None}

    users, groups, apps, auth_servers_map, resource_servers_map, mcp_servers_map = await asyncio.gather(
        resolve_all(user_ids, lambda id_: directory.get_user(client, id_)),
        resolve_all(group_ids, lambda id_: directory.get_group(client, id_)),
        resolve_all(app_ids, lambda id_: directory.get_app(client, id_)),
        resolve_all(auth_server_ids, lambda id_: directory.get_authorization_server(client, id_)),
        resolve_all(resource_server_ids, lambda id_: resource_servers.get_resource_server(client, id_)),
        resolve_all(mcp_server_ids, lambda id_: mcp_servers.get_mcp_server(client, id_)),
    )

    providers_list = await ai_agents.list_ai_agent_providers(client) if provider_ids else []
    providers_map: dict[str, ProviderDTO] = {p.id: p for p in providers_list if p.id in provider_ids}

    return assemble_graph(
        org_domain=session.org_domain,
        generated_at=datetime.now(timezone.utc).isoformat(),
        agents=agents,
        connections_by_agent=connections_by_agent,
        delegations_by_agent=delegations_by_agent,
        agent_orn_to_id=agent_orn_to_id,
        users=users,
        groups=groups,
        apps=apps,
        auth_servers=auth_servers_map,
        resource_servers=resource_servers_map,
        mcp_servers=mcp_servers_map,
        providers=providers_map,
        extra_warnings=warnings,
    )
