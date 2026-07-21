from app.graph.assemble import assemble_graph
from app.okta_client.models import AgentDTO, ConnectionDTO, DelegationLinkDTO, DirectoryObjectDTO, ProviderDTO


def make_agent(**overrides) -> AgentDTO:
    defaults = dict(id="wlp1", name="SalesAgent", status="ACTIVE", raw={"id": "wlp1"})
    defaults.update(overrides)
    return AgentDTO(**defaults)


def test_agent_node_and_owner_edge():
    agent = make_agent(owner_user_ids=["user1"])
    users = {"user1": DirectoryObjectDTO(id="user1", label="Sarah", raw={})}

    result = assemble_graph(
        org_domain="acme.okta.com", generated_at="2026-01-01T00:00:00Z",
        agents=[agent], connections_by_agent={}, delegations_by_agent={},
        agent_orn_to_id={}, users=users, groups={}, apps={}, auth_servers={},
        resource_servers={}, mcp_servers={}, providers={},
    )

    node_ids = {n.data.id for n in result.nodes}
    assert "agent:wlp1" in node_ids
    assert "user:user1" in node_ids

    owner_edges = [e for e in result.edges if e.data.type == "owner"]
    assert len(owner_edges) == 1
    assert owner_edges[0].data.source == "user:user1"
    assert owner_edges[0].data.target == "agent:wlp1"
    assert result.warnings == []


def test_unresolved_owner_produces_warning_not_crash():
    agent = make_agent(owner_user_ids=["ghost-user"])

    result = assemble_graph(
        org_domain="acme.okta.com", generated_at="2026-01-01T00:00:00Z",
        agents=[agent], connections_by_agent={}, delegations_by_agent={},
        agent_orn_to_id={}, users={}, groups={}, apps={}, auth_servers={},
        resource_servers={}, mcp_servers={}, providers={},
    )

    assert len(result.edges) == 0
    assert any("ghost-user" in w for w in result.warnings)


def test_authorization_server_connection_edge():
    agent = make_agent()
    connection = ConnectionDTO(
        id="mcn1", agent_id="wlp1", connection_type="IDENTITY_ASSERTION_CUSTOM_AS",
        status="ACTIVE", authorization_server_id="aus1", scope_condition="INCLUDE_ONLY",
        scopes=["mcp:read", "mcp:write"], raw={"authorizationServer": {"name": "Fallback AS", "issuerUrl": "https://x"}},
    )
    auth_servers = {"aus1": DirectoryObjectDTO(id="aus1", label="Sales AS", sub_label="https://acme.okta.com/oauth2/aus1", raw={})}

    result = assemble_graph(
        org_domain="acme.okta.com", generated_at="t", agents=[agent],
        connections_by_agent={"wlp1": [connection]}, delegations_by_agent={},
        agent_orn_to_id={}, users={}, groups={}, apps={}, auth_servers=auth_servers,
        resource_servers={}, mcp_servers={}, providers={},
    )

    node_ids = {n.data.id for n in result.nodes}
    assert "authorizationServer:aus1" in node_ids
    conn_edges = [e for e in result.edges if e.data.type == "connection"]
    assert len(conn_edges) == 1
    assert conn_edges[0].data.label == "Only allow: mcp:read, mcp:write"
    assert conn_edges[0].data.target == "authorizationServer:aus1"


def test_secret_connection_keyed_per_connection_not_deduplicated():
    agent = make_agent()
    conn_a = ConnectionDTO(id="mcn1", agent_id="wlp1", connection_type="STS_VAULT_SECRET", status="ACTIVE", resource_indicator="shared-api-key", raw={})
    conn_b = ConnectionDTO(id="mcn2", agent_id="wlp1", connection_type="STS_VAULT_SECRET", status="ACTIVE", resource_indicator="shared-api-key", raw={})

    result = assemble_graph(
        org_domain="acme.okta.com", generated_at="t", agents=[agent],
        connections_by_agent={"wlp1": [conn_a, conn_b]}, delegations_by_agent={},
        agent_orn_to_id={}, users={}, groups={}, apps={}, auth_servers={},
        resource_servers={}, mcp_servers={}, providers={},
    )

    secret_nodes = [n for n in result.nodes if n.data.type == "secret"]
    assert len(secret_nodes) == 2  # not deduplicated, even though the label is identical


def test_agent_to_agent_delegation_edge():
    caller = make_agent(id="wlp-caller", name="Caller", orn="orn:okta:idp:org1:workload-principals:ai-agents:wlp-caller")
    callee = make_agent(id="wlp-callee", name="Callee", orn="orn:okta:idp:org1:workload-principals:ai-agents:wlp-callee")
    delegation = DelegationLinkDTO(
        id="dlk1",
        from_client_orn="orn:okta:idp:org1:workload-principals:ai-agents:wlp-caller",
        to_authorization_server_orn="orn:okta:idp:org1:...:aus1",
        to_resource_orn="orn:okta:idp:org1:workload-principals:ai-agents:wlp-callee",
        raw={},
    )

    result = assemble_graph(
        org_domain="acme.okta.com", generated_at="t", agents=[caller, callee],
        connections_by_agent={}, delegations_by_agent={"wlp-callee": [delegation]},
        agent_orn_to_id={
            "orn:okta:idp:org1:workload-principals:ai-agents:wlp-caller": "wlp-caller",
            "orn:okta:idp:org1:workload-principals:ai-agents:wlp-callee": "wlp-callee",
        },
        users={}, groups={}, apps={}, auth_servers={}, resource_servers={}, mcp_servers={}, providers={},
    )

    delegation_edges = [e for e in result.edges if e.data.type == "delegation"]
    assert len(delegation_edges) == 1
    assert delegation_edges[0].data.source == "agent:wlp-caller"
    assert delegation_edges[0].data.target == "agent:wlp-callee"


def test_human_caller_delegation_is_skipped():
    callee = make_agent(id="wlp-callee", orn="orn:okta:idp:org1:workload-principals:ai-agents:wlp-callee")
    delegation = DelegationLinkDTO(
        id="dlk1",
        from_client_orn="orn:okta:idp:org1:apps:oidc_client:0oa123",  # a human/app caller, not an agent
        to_authorization_server_orn="orn:okta:idp:org1:...:aus1",
        to_resource_orn="orn:okta:idp:org1:workload-principals:ai-agents:wlp-callee",
        raw={},
    )

    result = assemble_graph(
        org_domain="acme.okta.com", generated_at="t", agents=[callee],
        connections_by_agent={}, delegations_by_agent={"wlp-callee": [delegation]},
        agent_orn_to_id={"orn:okta:idp:org1:workload-principals:ai-agents:wlp-callee": "wlp-callee"},
        users={}, groups={}, apps={}, auth_servers={}, resource_servers={}, mcp_servers={}, providers={},
    )

    assert [e for e in result.edges if e.data.type == "delegation"] == []


def test_imported_from_provider_edge():
    agent = make_agent(provider_id="aip1")
    providers = {"aip1": ProviderDTO(id="aip1", source_name="amazon_aws_sso", raw={})}

    result = assemble_graph(
        org_domain="acme.okta.com", generated_at="t", agents=[agent],
        connections_by_agent={}, delegations_by_agent={}, agent_orn_to_id={},
        users={}, groups={}, apps={}, auth_servers={}, resource_servers={}, mcp_servers={}, providers=providers,
    )

    imported_edges = [e for e in result.edges if e.data.type == "importedFrom"]
    assert len(imported_edges) == 1
    assert imported_edges[0].data.source == "provider:aip1"
    assert imported_edges[0].data.target == "agent:wlp1"
