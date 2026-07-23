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
    PolicyRuleGrantDTO,
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
        description: str | None = None,
        app_catalog_key: str | None = None,
        raw: dict | None = None,
        admin_url_override: str | None = None,
        imported: bool = False,
    ) -> str:
        node_id = _node_id(node_type, okta_id)
        if node_id not in self.nodes:
            self.nodes[node_id] = NodeData(
                id=node_id,
                type=node_type,  # type: ignore[arg-type]
                label=label,
                status=status,
                sub_label=sub_label,
                description=description,
                okta_id=okta_id,
                admin_url=admin_url_override or build_admin_url(self.org_domain, node_type, okta_id, app_catalog_key),  # type: ignore[arg-type]
                imported=imported,
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
        rule_summaries: list[str] | None = None,
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
                rule_summaries=rule_summaries or [],
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
    if (
        connection.connection_type in ("IDENTITY_ASSERTION_CUSTOM_AS", "IDENTITY_ASSERTION_A2A_SERVER")
        and connection.scope_condition
    ):
        ui_label = {"ALL_SCOPES": "Allow all", "INCLUDE_ONLY": "Only allow", "EXCLUDE": "Disallow"}.get(
            connection.scope_condition, connection.scope_condition
        )
        if connection.scopes:
            return f"{ui_label}: {', '.join(connection.scopes)}"
        return ui_label
    return connection.status


def _rule_summary(grant: PolicyRuleGrantDTO) -> str:
    policy = grant.policy_name or "Unnamed policy"
    rule = grant.rule_name or "Unnamed rule"
    scope_text = "all scopes" if "*" in grant.scopes else (", ".join(grant.scopes) if grant.scopes else "no scopes")
    return f"{policy} → {rule}: grants {scope_text}"


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
    providers: dict[str, ProviderDTO],
    app_groups: dict[str, list[str]] | None = None,
    auth_server_policy_grants: dict[str, dict[str, list[PolicyRuleGrantDTO]]] | None = None,
    extra_warnings: list[str] | None = None,
) -> GraphResponse:
    builder = _GraphBuilder(org_domain)
    builder.warnings.extend(extra_warnings or [])

    agent_ids = {a.id for a in agents}

    for agent in agents:
        agent_node_id = builder.add_node(
            "agent", agent.id, agent.name, status=agent.status, sub_label=agent.platform,
            description=agent.description, raw=agent.raw, imported=agent.provider_id is not None,
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
                # source_name is only the generic OIN catalog key (e.g.
                # "amazon_aws_sso") shared by every org using that IdP type —
                # prefer the org's own admin-assigned label on the linked
                # Application when it resolved, keeping source_name visible
                # as the sub_label rather than discarding it.
                linked_app = apps.get(provider.linked_app_id) if provider.linked_app_id else None
                label = linked_app.label if linked_app else provider.source_name
                sub_label = provider.source_name if linked_app else None
                provider_node_id = builder.add_node(
                    "provider", provider.id, label, sub_label=sub_label, raw=provider.raw,
                )
                builder.add_edge(
                    f"importedFrom:{agent.id}", provider_node_id, agent_node_id, "importedFrom",
                    label="Imported from",
                )

        # Resource connections
        for connection in connections_by_agent.get(agent.id, []):
            target_node_id = _resolve_connection_target(builder, connection, auth_servers, apps, agent_ids)
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

    # Groups assigned to a referenced app, and groups referenced by Access
    # Policy Rules on a referenced custom Authorization Server. Runs after the
    # main loop so every application/authorizationServer node it might attach
    # to already exists; silently skips ids that were never actually rendered
    # (e.g. an app_id that came back empty from the by-id lookup).
    for app_id, group_ids in (app_groups or {}).items():
        app_node_id = _node_id("application", app_id)
        if app_node_id not in builder.nodes:
            continue
        for group_id in group_ids:
            group = groups.get(group_id)
            if group is None:
                builder.warnings.append(f"application {app_id}: assigned group {group_id} could not be resolved")
                continue
            group_node_id = builder.add_node("group", group.id, group.label, sub_label=group.sub_label, raw=group.raw)
            builder.add_edge(
                f"groupAssignment:{app_id}:{group_id}", group_node_id, app_node_id, "groupAssignment",
                label="Assigned",
            )

    for auth_server_id, group_grants in (auth_server_policy_grants or {}).items():
        as_node_id = _node_id("authorizationServer", auth_server_id)
        if as_node_id not in builder.nodes:
            continue
        for group_id, grants in group_grants.items():
            group = groups.get(group_id)
            if group is None:
                builder.warnings.append(
                    f"authorizationServer {auth_server_id}: policy group {group_id} could not be resolved"
                )
                continue
            group_node_id = builder.add_node("group", group.id, group.label, sub_label=group.sub_label, raw=group.raw)
            all_scopes = sorted({s for grant in grants for s in grant.scopes})
            builder.add_edge(
                f"accessPolicy:{auth_server_id}:{group_id}", group_node_id, as_node_id, "accessPolicy",
                label="Access policy",
                scopes=all_scopes,
                rule_summaries=[_rule_summary(g) for g in grants],
                raw={"grants": [g.model_dump() for g in grants]},
            )

    return builder.to_response(generated_at)


def _resolve_connection_target(
    builder: _GraphBuilder,
    connection: ConnectionDTO,
    auth_servers: dict[str, DirectoryObjectDTO],
    apps: dict[str, DirectoryObjectDTO],
    agent_ids: set[str],
) -> str | None:
    if connection.connection_type == "IDENTITY_ASSERTION_A2A_SERVER":
        # resource_id here is the target agent's own id (see
        # _extract_a2a_target_agent_id) — only draw the edge if that agent is
        # actually one of this graph's agents, so we never emit an edge to a
        # node that was never created.
        if connection.resource_id and connection.resource_id in agent_ids:
            return _node_id("agent", connection.resource_id)
        return None

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
        # No working by-id lookup exists for these two (the guessed
        # /api/v1/resource-servers and /api/v1/mcp-servers endpoints 405 live)
        # — the connection's embedded `resource` object is the only source of
        # a name, confirmed against a live tenant.
        if connection.resource_type == "API_SERVER" and connection.resource_id:
            resource = connection.raw.get("resource", {})
            label = resource.get("name", connection.resource_id)
            return builder.add_node(
                "resourceServer", connection.resource_id, label,
                sub_label=resource.get("resourceUrl"), raw=resource,
            )
        if connection.resource_type == "MCP_SERVER" and connection.resource_id:
            resource = connection.raw.get("resource", {})
            label = resource.get("name", connection.resource_id)
            return builder.add_node(
                "mcpServer", connection.resource_id, label,
                sub_label=resource.get("endpointUrl"), raw=resource,
            )
        return None

    if connection.connection_type == "STS_VAULT_SECRET":
        secret = connection.raw.get("secret", {})
        label = secret.get("name") or connection.resource_indicator or connection.id
        # secret._links.web.href is a full, already-qualified URL into the
        # OPA (Privileged Access) vault UI — a different domain/product than
        # the Admin Console, so it can't be derived from org_domain + id.
        web_url = secret.get("_links", {}).get("web", {}).get("href") or None
        return builder.add_node(
            "secret", connection.id, label, status=connection.status, raw=connection.raw,
            admin_url_override=web_url,
        )

    if connection.connection_type == "STS_SERVICE_ACCOUNT":
        # Label shape confirmed live: an embedded `serviceAccount` object
        # with `name`, same as STS_VAULT_SECRET. Its `_links.web.href` is
        # NOT used, though — confirmed live to be a dead link
        # (/t/{tenant}/saas_apps/{appId}/service_accounts/{id} 404s). The
        # real OPA console URL needs a resourceGroupId/projectId that never
        # appears anywhere in this payload, so there's no way to construct
        # a working link from data available here.
        service_account = connection.raw.get("serviceAccount", {})
        label = service_account.get("name") or connection.resource_indicator or connection.id
        return builder.add_node("serviceAccount", connection.id, label, status=connection.status, raw=connection.raw)

    return None
