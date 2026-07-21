"""Pure aggregation: raw DTOs in, GraphResponse out. No I/O, no side effects —
unit-testable with fixture JSON, no live org required (see tests/test_assemble.py).

Design decisions baked in here (see plan for the reasoning):
- JWKs are never rendered as nodes (agent detail-panel data only).
- Secret/Service Account nodes are keyed per-connection, not deduplicated
  across agents (no OPA integration in v1 to tell us they're "the same" secret).
- Application (APP_INSTANCE) and Resource Server (API_SERVER) get distinct
  node types even though the Admin UI labels both "Application".
- A2A delegation edges are drawn directly agent->agent; the intermediating
  authorization server ORN is kept in the edge's `raw`, not rendered as an
  extra node/hop.
"""

from app.graph.contract import EdgeData, GraphEdge, GraphNode, GraphResponse, NodeData
from app.graph.deeplinks import build_admin_url
from app.okta_client.models import (
    AgentDTO,
    ConnectionDTO,
    DelegationLinkDTO,
    DirectoryObjectDTO,
    ProviderDTO,
)


def _node_id(node_type: str, okta_id: str) -> str:
    return f"{node_type}:{okta_id}"


class _GraphBuilder:
    def __init__(self, org_domain: str) -> None:
        self.org_domain = org_domain
        self.nodes: dict[str, NodeData] = {}
        self.edges: list[EdgeData] = []
        self.warnings: list[str] = []

    def add_node(
        self,
        node_type: str,
        okta_id: str,
        label: str,
        status: str | None = None,
        sub_label: str | None = None,
        app_catalog_key: str | None = None,
        raw: dict | None = None,
    ) -> str:
        node_id = _node_id(node_type, okta_id)
        if node_id not in self.nodes:
            self.nodes[node_id] = NodeData(
                id=node_id,
                type=node_type,  # type: ignore[arg-type]
                label=label,
                status=status,
                sub_label=sub_label,
                okta_id=okta_id,
                admin_url=build_admin_url(self.org_domain, node_type, okta_id, app_catalog_key),  # type: ignore[arg-type]
                raw=raw or {},
            )
        return node_id

    def add_edge(
        self,
        edge_id: str,
        source: str,
        target: str,
        edge_type: str,
        label: str | None = None,
        connection_type: str | None = None,
        status: str | None = None,
        scope_condition: str | None = None,
        scopes: list[str] | None = None,
        raw: dict | None = None,
    ) -> None:
        self.edges.append(
            EdgeData(
                id=edge_id,
                source=source,
                target=target,
                type=edge_type,  # type: ignore[arg-type]
                label=label,
                connection_type=connection_type,
                status=status,
                scope_condition=scope_condition,
                scopes=scopes or [],
                raw=raw or {},
            )
        )

    def to_response(self, generated_at: str) -> GraphResponse:
        return GraphResponse(
            generated_at=generated_at,
            org_domain=self.org_domain,
            nodes=[GraphNode(data=n) for n in self.nodes.values()],
            edges=[GraphEdge(data=e) for e in self.edges],
            warnings=self.warnings,
        )


def _connection_label(connection: ConnectionDTO) -> str:
    if connection.connection_type == "IDENTITY_ASSERTION_CUSTOM_AS" and connection.scope_condition:
        ui_label = {"ALL_SCOPES": "Allow all", "INCLUDE_ONLY": "Only allow", "EXCLUDE": "Disallow"}.get(
            connection.scope_condition, connection.scope_condition
        )
        if connection.scopes:
            return f"{ui_label}: {', '.join(connection.scopes)}"
        return ui_label
    return connection.status


def assemble_graph(
    *,
    org_domain: str,
    generated_at: str,
    agents: list[AgentDTO],
    connections_by_agent: dict[str, list[ConnectionDTO]],
    delegations_by_agent: dict[str, list[DelegationLinkDTO]],
    agent_orn_to_id: dict[str, str],
    users: dict[str, DirectoryObjectDTO],
    groups: dict[str, DirectoryObjectDTO],
    apps: dict[str, DirectoryObjectDTO],
    auth_servers: dict[str, DirectoryObjectDTO],
    resource_servers: dict[str, DirectoryObjectDTO],
    mcp_servers: dict[str, DirectoryObjectDTO],
    providers: dict[str, ProviderDTO],
    extra_warnings: list[str] | None = None,
) -> GraphResponse:
    builder = _GraphBuilder(org_domain)
    builder.warnings.extend(extra_warnings or [])

    agent_ids = {a.id for a in agents}

    for agent in agents:
        agent_node_id = builder.add_node(
            "agent", agent.id, agent.name, status=agent.status, sub_label=agent.platform, raw=agent.raw
        )

        # Owners
        for user_id in agent.owner_user_ids:
            user = users.get(user_id)
            if user is None:
                builder.warnings.append(f"agent {agent.id}: owner user {user_id} could not be resolved")
                continue
            user_node_id = builder.add_node("user", user.id, user.label, status=user.status, sub_label=user.sub_label, raw=user.raw)
            builder.add_edge(f"owner:{agent.id}:{user_id}", user_node_id, agent_node_id, "owner", label="Owner")

        if agent.owner_group_id:
            group = groups.get(agent.owner_group_id)
            if group is None:
                builder.warnings.append(f"agent {agent.id}: owner group {agent.owner_group_id} could not be resolved")
            else:
                group_node_id = builder.add_node("group", group.id, group.label, sub_label=group.sub_label, raw=group.raw)
                builder.add_edge(f"owner:{agent.id}:{group.id}", group_node_id, agent_node_id, "owner", label="Owner")

        # Linked app (user sign-on)
        if agent.linked_app_id:
            linked_app = apps.get(agent.linked_app_id)
            if linked_app is None:
                builder.warnings.append(f"agent {agent.id}: linked app {agent.linked_app_id} could not be resolved")
            else:
                app_node_id = builder.add_node(
                    "application", linked_app.id, linked_app.label, status=linked_app.status,
                    app_catalog_key=linked_app.sub_label, raw=linked_app.raw,
                )
                builder.add_edge(
                    f"linkedApp:{agent.id}:{linked_app.id}", agent_node_id, app_node_id, "linkedApp",
                    label="Linked app (user sign-on)",
                )

        # Imported from provider
        if agent.provider_id:
            provider = providers.get(agent.provider_id)
            if provider is None:
                builder.warnings.append(f"agent {agent.id}: provider {agent.provider_id} could not be resolved")
            else:
                provider_node_id = builder.add_node("provider", provider.id, provider.source_name, raw=provider.raw)
                builder.add_edge(
                    f"importedFrom:{agent.id}", provider_node_id, agent_node_id, "importedFrom",
                    label="Imported from",
                )

        # Resource connections
        for connection in connections_by_agent.get(agent.id, []):
            target_node_id = _resolve_connection_target(
                builder, connection, auth_servers, apps, resource_servers, mcp_servers
            )
            if target_node_id is None:
                builder.warnings.append(
                    f"agent {agent.id}: connection {connection.id} ({connection.connection_type}) "
                    "could not be resolved to a target node"
                )
                continue
            builder.add_edge(
                f"connection:{connection.id}",
                agent_node_id,
                target_node_id,
                "connection",
                label=_connection_label(connection),
                connection_type=connection.connection_type,
                status=connection.status,
                scope_condition=connection.scope_condition,
                scopes=connection.scopes,
                raw=connection.raw,
            )

        # Agent-to-agent delegations (this agent is the callee / `to` side)
        for delegation in delegations_by_agent.get(agent.id, []):
            from_agent_id = agent_orn_to_id.get(delegation.from_client_orn)
            if from_agent_id is None or from_agent_id not in agent_ids:
                # Not an agent-to-agent delegation (human/app OIDC client caller) — out of scope for v1.
                continue
            from_node_id = _node_id("agent", from_agent_id)
            builder.add_edge(
                f"delegation:{delegation.id}", from_node_id, agent_node_id, "delegation",
                label="Delegates to", raw=delegation.raw,
            )

    return builder.to_response(generated_at)


def _resolve_connection_target(
    builder: _GraphBuilder,
    connection: ConnectionDTO,
    auth_servers: dict[str, DirectoryObjectDTO],
    apps: dict[str, DirectoryObjectDTO],
    resource_servers: dict[str, DirectoryObjectDTO],
    mcp_servers: dict[str, DirectoryObjectDTO],
) -> str | None:
    if connection.connection_type == "IDENTITY_ASSERTION_CUSTOM_AS":
        if not connection.authorization_server_id:
            return None
        auth_server = auth_servers.get(connection.authorization_server_id)
        raw_auth_server = connection.raw.get("authorizationServer", {})
        label = auth_server.label if auth_server else raw_auth_server.get("name", connection.authorization_server_id)
        sub_label = auth_server.sub_label if auth_server else raw_auth_server.get("issuerUrl")
        return builder.add_node(
            "authorizationServer", connection.authorization_server_id, label, sub_label=sub_label,
            raw=(auth_server.raw if auth_server else raw_auth_server),
        )

    if connection.connection_type == "STS_ACCESS_TOKEN":
        if connection.resource_type == "APP_INSTANCE" and connection.resource_id:
            app = apps.get(connection.resource_id)
            label = app.label if app else connection.resource_id
            return builder.add_node(
                "application", connection.resource_id, label,
                status=app.status if app else None, app_catalog_key=app.sub_label if app else None,
                raw=app.raw if app else {},
            )
        if connection.resource_type == "API_SERVER" and connection.resource_id:
            rs = resource_servers.get(connection.resource_id)
            label = rs.label if rs else connection.resource_id
            return builder.add_node(
                "resourceServer", connection.resource_id, label,
                status=rs.status if rs else None, sub_label=rs.sub_label if rs else None,
                raw=rs.raw if rs else {},
            )
        if connection.resource_type == "MCP_SERVER" and connection.resource_id:
            mcp = mcp_servers.get(connection.resource_id)
            label = mcp.label if mcp else connection.resource_id
            return builder.add_node(
                "mcpServer", connection.resource_id, label,
                status=mcp.status if mcp else None, sub_label=mcp.sub_label if mcp else None,
                raw=mcp.raw if mcp else {},
            )
        return None

    if connection.connection_type == "STS_VAULT_SECRET":
        label = connection.resource_indicator or connection.id
        return builder.add_node("secret", connection.id, label, status=connection.status, raw=connection.raw)

    if connection.connection_type == "STS_SERVICE_ACCOUNT":
        label = connection.resource_indicator or connection.id
        return builder.add_node("serviceAccount", connection.id, label, status=connection.status, raw=connection.raw)

    return None
