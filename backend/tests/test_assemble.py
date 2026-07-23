from app.graph.assemble import assemble_graph
from app.okta_client.models import (
    AgentDTO,
    ConnectionDTO,
    DelegationLinkDTO,
    DirectoryObjectDTO,
    PolicyRuleGrantDTO,
    ProviderDTO,
)


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
        providers={},
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
        providers={},
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
        providers={},
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
        providers={},
    )

    secret_nodes = [n for n in result.nodes if n.data.type == "secret"]
    assert len(secret_nodes) == 2  # not deduplicated, even though the label is identical


def test_secret_connection_uses_embedded_name_and_web_link():
    agent = make_agent()
    connection = ConnectionDTO(
        id="mcn1", agent_id="wlp1", connection_type="STS_VAULT_SECRET", status="ACTIVE",
        resource_indicator="orn:oktapreview:pam:org1:secrets:5cdcda01",
        raw={
            "secret": {
                "name": "ausFDClist-DB-Creds",
                "_links": {"web": {"href": "https://acme.pam.oktapreview.com/t/acme/secrets/secret/5cdcda01"}},
            }
        },
    )

    result = assemble_graph(
        org_domain="acme.okta.com", generated_at="t", agents=[agent],
        connections_by_agent={"wlp1": [connection]}, delegations_by_agent={},
        agent_orn_to_id={}, users={}, groups={}, apps={}, auth_servers={},
        providers={},
    )

    secret_node = next(n for n in result.nodes if n.data.type == "secret")
    assert secret_node.data.label == "ausFDClist-DB-Creds"
    assert secret_node.data.admin_url == "https://acme.pam.oktapreview.com/t/acme/secrets/secret/5cdcda01"


def test_service_account_connection_uses_embedded_name_but_no_admin_url():
    agent = make_agent()
    connection = ConnectionDTO(
        id="mcn1", agent_id="wlp1", connection_type="STS_SERVICE_ACCOUNT", status="ACTIVE",
        resource_indicator="orn:oktapreview:pam:org1:apps:bookmark:0oa1:service_accounts:cc75c111",
        raw={
            "serviceAccount": {
                "name": "Marketing User",
                # Okta's own embedded web link here is confirmed live to be
                # a dead URL (missing resourceGroupId/projectId that the
                # real OPA console needs) — deliberately not used as
                # admin_url_override, unlike the STS_VAULT_SECRET case.
                "_links": {"web": {"href": "https://acme.pam.oktapreview.com/t/acme/saas_apps/0oa1/service_accounts/cc75c111"}},
            }
        },
    )

    result = assemble_graph(
        org_domain="acme.okta.com", generated_at="t", agents=[agent],
        connections_by_agent={"wlp1": [connection]}, delegations_by_agent={},
        agent_orn_to_id={}, users={}, groups={}, apps={}, auth_servers={},
        providers={},
    )

    sa_node = next(n for n in result.nodes if n.data.type == "serviceAccount")
    assert sa_node.data.label == "Marketing User"
    assert sa_node.data.admin_url is None


def test_resource_server_and_mcp_server_use_embedded_resource_name():
    agent = make_agent()
    rs_connection = ConnectionDTO(
        id="mcn1", agent_id="wlp1", connection_type="STS_ACCESS_TOKEN", status="ACTIVE",
        resource_type="API_SERVER", resource_id="api1",
        raw={"resource": {"name": "Strava API", "resourceUrl": "https://mcp.strava.com/mcp", "resourceType": "API_SERVER"}},
    )
    mcp_connection = ConnectionDTO(
        id="mcn2", agent_id="wlp1", connection_type="STS_ACCESS_TOKEN", status="ACTIVE",
        resource_type="MCP_SERVER", resource_id="ems1",
        raw={"resource": {"name": "DAE Slack MCP", "endpointUrl": "https://mcp.slack.com/mcp", "resourceType": "MCP_SERVER"}},
    )

    result = assemble_graph(
        org_domain="acme.okta.com", generated_at="t", agents=[agent],
        connections_by_agent={"wlp1": [rs_connection, mcp_connection]}, delegations_by_agent={},
        agent_orn_to_id={}, users={}, groups={}, apps={}, auth_servers={},
        providers={},
    )

    rs_node = next(n for n in result.nodes if n.data.type == "resourceServer")
    mcp_node = next(n for n in result.nodes if n.data.type == "mcpServer")
    assert rs_node.data.label == "Strava API"
    assert mcp_node.data.label == "DAE Slack MCP"


def test_a2a_server_connection_edge():
    caller = make_agent(id="wlp-caller", name="Caller")
    callee = make_agent(id="wlp-callee", name="Callee")
    connection = ConnectionDTO(
        id="mcn1", agent_id="wlp-caller", connection_type="IDENTITY_ASSERTION_A2A_SERVER",
        status="ACTIVE", resource_id="wlp-callee", scope_condition="ALL_SCOPES", scopes=["*"], raw={},
    )

    result = assemble_graph(
        org_domain="acme.okta.com", generated_at="t", agents=[caller, callee],
        connections_by_agent={"wlp-caller": [connection]}, delegations_by_agent={},
        agent_orn_to_id={}, users={}, groups={}, apps={}, auth_servers={},
        providers={},
    )

    conn_edges = [e for e in result.edges if e.data.type == "connection"]
    assert len(conn_edges) == 1
    assert conn_edges[0].data.source == "agent:wlp-caller"
    assert conn_edges[0].data.target == "agent:wlp-callee"
    assert conn_edges[0].data.label == "Allow all: *"
    assert result.warnings == []


def test_a2a_server_connection_to_unknown_agent_produces_warning():
    caller = make_agent(id="wlp-caller", name="Caller")
    connection = ConnectionDTO(
        id="mcn1", agent_id="wlp-caller", connection_type="IDENTITY_ASSERTION_A2A_SERVER",
        status="ACTIVE", resource_id="wlp-not-in-graph", raw={},
    )

    result = assemble_graph(
        org_domain="acme.okta.com", generated_at="t", agents=[caller],
        connections_by_agent={"wlp-caller": [connection]}, delegations_by_agent={},
        agent_orn_to_id={}, users={}, groups={}, apps={}, auth_servers={},
        providers={},
    )

    assert [e for e in result.edges if e.data.type == "connection"] == []
    assert any("mcn1" in w for w in result.warnings)


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
        users={}, groups={}, apps={}, auth_servers={}, providers={},
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
        users={}, groups={}, apps={}, auth_servers={}, providers={},
    )

    assert [e for e in result.edges if e.data.type == "delegation"] == []


def test_app_group_assignment_edge():
    agent = make_agent(linked_app_id="app1")
    apps = {"app1": DirectoryObjectDTO(id="app1", label="Sales App", raw={})}
    groups = {"grp1": DirectoryObjectDTO(id="grp1", label="Sales Team", raw={})}

    result = assemble_graph(
        org_domain="acme.okta.com", generated_at="t", agents=[agent],
        connections_by_agent={}, delegations_by_agent={}, agent_orn_to_id={},
        users={}, groups=groups, apps=apps, auth_servers={},
        providers={}, app_groups={"app1": ["grp1"]},
    )

    node_ids = {n.data.id for n in result.nodes}
    assert "group:grp1" in node_ids
    assignment_edges = [e for e in result.edges if e.data.type == "groupAssignment"]
    assert len(assignment_edges) == 1
    assert assignment_edges[0].data.source == "group:grp1"
    assert assignment_edges[0].data.target == "application:app1"


def test_authorization_server_policy_group_edge():
    agent = make_agent()
    connection = ConnectionDTO(
        id="mcn1", agent_id="wlp1", connection_type="IDENTITY_ASSERTION_CUSTOM_AS",
        status="ACTIVE", authorization_server_id="aus1", raw={},
    )
    auth_servers = {"aus1": DirectoryObjectDTO(id="aus1", label="Sales AS", raw={})}
    groups = {"grp1": DirectoryObjectDTO(id="grp1", label="Sales Team", raw={})}
    grant = PolicyRuleGrantDTO(
        policy_name="Default Policy", rule_name="Allow Sales Team",
        rule_status="ACTIVE", grant_types=["client_credentials"], scopes=["inventory.read"],
        raw={"policy": {}, "rule": {}},
    )

    result = assemble_graph(
        org_domain="acme.okta.com", generated_at="t", agents=[agent],
        connections_by_agent={"wlp1": [connection]}, delegations_by_agent={}, agent_orn_to_id={},
        users={}, groups=groups, apps={}, auth_servers=auth_servers,
        providers={}, auth_server_policy_grants={"aus1": {"grp1": [grant]}},
    )

    node_ids = {n.data.id for n in result.nodes}
    assert "group:grp1" in node_ids
    policy_edges = [e for e in result.edges if e.data.type == "accessPolicy"]
    assert len(policy_edges) == 1
    assert policy_edges[0].data.source == "group:grp1"
    assert policy_edges[0].data.target == "authorizationServer:aus1"
    assert policy_edges[0].data.scopes == ["inventory.read"]
    assert policy_edges[0].data.rule_summaries == ["Default Policy → Allow Sales Team: grants inventory.read"]
    assert policy_edges[0].data.raw["grants"][0]["rule_name"] == "Allow Sales Team"


def test_imported_from_provider_edge():
    agent = make_agent(provider_id="aip1")
    providers = {"aip1": ProviderDTO(id="aip1", source_name="amazon_aws_sso", raw={})}

    result = assemble_graph(
        org_domain="acme.okta.com", generated_at="t", agents=[agent],
        connections_by_agent={}, delegations_by_agent={}, agent_orn_to_id={},
        users={}, groups={}, apps={}, auth_servers={}, providers=providers,
    )

    imported_edges = [e for e in result.edges if e.data.type == "importedFrom"]
    assert len(imported_edges) == 1
    assert imported_edges[0].data.source == "provider:aip1"
    assert imported_edges[0].data.target == "agent:wlp1"

    agent_node = next(n for n in result.nodes if n.data.id == "agent:wlp1")
    assert agent_node.data.imported is True


def test_provider_node_prefers_linked_app_label_over_source_name():
    agent = make_agent(provider_id="aip1")
    providers = {
        "aip1": ProviderDTO(id="aip1", source_name="amazon_aws_sso", linked_app_id="0oaabc", raw={}),
    }
    apps = {"0oaabc": DirectoryObjectDTO(id="0oaabc", label="AWS IAM Identity Center", raw={})}

    result = assemble_graph(
        org_domain="acme.okta.com", generated_at="t", agents=[agent],
        connections_by_agent={}, delegations_by_agent={}, agent_orn_to_id={},
        users={}, groups={}, apps=apps, auth_servers={}, providers=providers,
    )

    provider_node = next(n for n in result.nodes if n.data.id == "provider:aip1")
    assert provider_node.data.label == "AWS IAM Identity Center"
    assert provider_node.data.sub_label == "amazon_aws_sso"


def test_provider_node_falls_back_to_source_name_when_app_unresolved():
    agent = make_agent(provider_id="aip1")
    providers = {
        "aip1": ProviderDTO(id="aip1", source_name="amazon_aws_sso", linked_app_id="0oaabc", raw={}),
    }

    result = assemble_graph(
        org_domain="acme.okta.com", generated_at="t", agents=[agent],
        connections_by_agent={}, delegations_by_agent={}, agent_orn_to_id={},
        users={}, groups={}, apps={}, auth_servers={}, providers=providers,
    )

    provider_node = next(n for n in result.nodes if n.data.id == "provider:aip1")
    assert provider_node.data.label == "amazon_aws_sso"
    assert provider_node.data.sub_label is None


def test_manually_created_agent_is_not_flagged_imported():
    agent = make_agent(description="Sales assistant")

    result = assemble_graph(
        org_domain="acme.okta.com", generated_at="t", agents=[agent],
        connections_by_agent={}, delegations_by_agent={}, agent_orn_to_id={},
        users={}, groups={}, apps={}, auth_servers={}, providers={},
    )

    agent_node = next(n for n in result.nodes if n.data.id == "agent:wlp1")
    assert agent_node.data.imported is False
    assert agent_node.data.description == "Sales assistant"
