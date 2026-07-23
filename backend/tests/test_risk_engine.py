from app.okta_client.models import AgentDTO, ConnectionDTO, DelegationLinkDTO, PolicyRuleGrantDTO
from app.risk.context import RiskContext
from app.risk.rules import (
    RULE_BROKEN_A2A_ID,
    RULE_EVERYONE_ON_APP_ID,
    RULE_EVERYONE_ON_POLICY_ID,
    RULE_HIGH_PCT_USERS_ID,
    RULE_INACTIVE_DOWNSTREAM_ID,
    RULE_NO_OWNERS_ID,
    RULE_SECRETS_OR_SERVICE_ACCOUNTS_ID,
    evaluate_risks,
)


def make_agent(**overrides) -> AgentDTO:
    defaults = dict(id="wlp1", name="SalesAgent", status="ACTIVE", raw={"id": "wlp1"})
    defaults.update(overrides)
    return AgentDTO(**defaults)


def make_ctx(**overrides) -> RiskContext:
    defaults = dict(
        agents=[],
        connections_by_agent={},
        delegations_by_agent={},
        agent_orn_to_id={},
        groups={},
        apps={},
        auth_servers={},
        app_groups={},
        auth_server_policy_grants={},
        everyone_group_id=None,
        org_user_count=None,
        app_member_user_ids={},
    )
    defaults.update(overrides)
    return RiskContext(**defaults)


def ids_for(ctx: RiskContext, rule_id: str) -> list[str]:
    return [f.agent_id for f in evaluate_risks(ctx) if f.rule_id == rule_id]


def test_everyone_group_on_app_flagged():
    agent = make_agent(linked_app_id="app1")
    ctx = make_ctx(agents=[agent], app_groups={"app1": ["everyone-grp"]}, everyone_group_id="everyone-grp")

    assert ids_for(ctx, RULE_EVERYONE_ON_APP_ID) == ["wlp1"]


def test_non_everyone_group_on_app_not_flagged():
    agent = make_agent(linked_app_id="app1")
    ctx = make_ctx(agents=[agent], app_groups={"app1": ["other-grp"]}, everyone_group_id="everyone-grp")

    assert ids_for(ctx, RULE_EVERYONE_ON_APP_ID) == []


def test_everyone_group_on_policy_flagged():
    agent = make_agent()
    connection = ConnectionDTO(
        id="mcn1", agent_id="wlp1", connection_type="IDENTITY_ASSERTION_CUSTOM_AS",
        status="ACTIVE", authorization_server_id="aus1", raw={},
    )
    grant = PolicyRuleGrantDTO(policy_name="Default Policy", rule_name="Allow Everyone", raw={})
    ctx = make_ctx(
        agents=[agent], connections_by_agent={"wlp1": [connection]},
        auth_server_policy_grants={"aus1": {"everyone-grp": [grant]}}, everyone_group_id="everyone-grp",
    )

    assert ids_for(ctx, RULE_EVERYONE_ON_POLICY_ID) == ["wlp1"]


def test_policy_without_everyone_grant_not_flagged():
    agent = make_agent()
    connection = ConnectionDTO(
        id="mcn1", agent_id="wlp1", connection_type="IDENTITY_ASSERTION_CUSTOM_AS",
        status="ACTIVE", authorization_server_id="aus1", raw={},
    )
    grant = PolicyRuleGrantDTO(policy_name="Default Policy", rule_name="Allow Sales Team", raw={})
    ctx = make_ctx(
        agents=[agent], connections_by_agent={"wlp1": [connection]},
        auth_server_policy_grants={"aus1": {"sales-grp": [grant]}}, everyone_group_id="everyone-grp",
    )

    assert ids_for(ctx, RULE_EVERYONE_ON_POLICY_ID) == []


def test_high_pct_users_flagged_above_80_percent():
    agent = make_agent(linked_app_id="app1")
    ctx = make_ctx(
        agents=[agent], app_member_user_ids={"app1": {f"u{i}" for i in range(9)}}, org_user_count=10,
    )

    assert ids_for(ctx, RULE_HIGH_PCT_USERS_ID) == ["wlp1"]


def test_high_pct_users_not_flagged_at_or_below_80_percent():
    agent = make_agent(linked_app_id="app1")
    ctx = make_ctx(
        agents=[agent], app_member_user_ids={"app1": {f"u{i}" for i in range(8)}}, org_user_count=10,
    )

    assert ids_for(ctx, RULE_HIGH_PCT_USERS_ID) == []


def test_high_pct_users_skipped_when_org_user_count_unknown():
    agent = make_agent(linked_app_id="app1")
    ctx = make_ctx(agents=[agent], app_member_user_ids={"app1": {"u1", "u2"}}, org_user_count=None)

    assert ids_for(ctx, RULE_HIGH_PCT_USERS_ID) == []


def test_secret_or_service_account_connection_flagged_once_per_agent():
    agent = make_agent()
    conn_a = ConnectionDTO(id="mcn1", agent_id="wlp1", connection_type="STS_VAULT_SECRET", status="ACTIVE", raw={})
    conn_b = ConnectionDTO(id="mcn2", agent_id="wlp1", connection_type="STS_SERVICE_ACCOUNT", status="ACTIVE", raw={})
    ctx = make_ctx(agents=[agent], connections_by_agent={"wlp1": [conn_a, conn_b]})

    assert ids_for(ctx, RULE_SECRETS_OR_SERVICE_ACCOUNTS_ID) == ["wlp1"]


def test_no_secrets_or_service_accounts_not_flagged():
    agent = make_agent()
    connection = ConnectionDTO(id="mcn1", agent_id="wlp1", connection_type="STS_ACCESS_TOKEN", status="ACTIVE", raw={})
    ctx = make_ctx(agents=[agent], connections_by_agent={"wlp1": [connection]})

    assert ids_for(ctx, RULE_SECRETS_OR_SERVICE_ACCOUNTS_ID) == []


def test_broken_a2a_connection_flagged_and_anchored_on_inactive_target():
    caller = make_agent(id="wlp-caller", name="Caller", status="ACTIVE")
    callee = make_agent(id="wlp-callee", name="Callee", status="SUSPENDED")
    connection = ConnectionDTO(
        id="mcn1", agent_id="wlp-caller", connection_type="IDENTITY_ASSERTION_A2A_SERVER",
        status="ACTIVE", resource_id="wlp-callee", raw={},
    )
    ctx = make_ctx(agents=[caller, callee], connections_by_agent={"wlp-caller": [connection]})

    assert ids_for(ctx, RULE_BROKEN_A2A_ID) == ["wlp-callee"]


def test_broken_a2a_connections_from_multiple_callers_consolidated_on_inactive_target():
    caller_a = make_agent(id="wlp-caller-a", name="Caller A", status="ACTIVE")
    caller_b = make_agent(id="wlp-caller-b", name="Caller B", status="ACTIVE")
    callee = make_agent(id="wlp-callee", name="Callee", status="SUSPENDED")
    conn_a = ConnectionDTO(
        id="mcn1", agent_id="wlp-caller-a", connection_type="IDENTITY_ASSERTION_A2A_SERVER",
        status="ACTIVE", resource_id="wlp-callee", raw={},
    )
    conn_b = ConnectionDTO(
        id="mcn2", agent_id="wlp-caller-b", connection_type="IDENTITY_ASSERTION_A2A_SERVER",
        status="ACTIVE", resource_id="wlp-callee", raw={},
    )
    ctx = make_ctx(
        agents=[caller_a, caller_b, callee],
        connections_by_agent={"wlp-caller-a": [conn_a], "wlp-caller-b": [conn_b]},
    )

    findings = [f for f in evaluate_risks(ctx) if f.rule_id == RULE_BROKEN_A2A_ID]
    assert [f.agent_id for f in findings] == ["wlp-callee"]
    assert "Caller A" in findings[0].detail
    assert "Caller B" in findings[0].detail


def test_active_a2a_connection_not_flagged():
    caller = make_agent(id="wlp-caller", name="Caller", status="ACTIVE")
    callee = make_agent(id="wlp-callee", name="Callee", status="ACTIVE")
    connection = ConnectionDTO(
        id="mcn1", agent_id="wlp-caller", connection_type="IDENTITY_ASSERTION_A2A_SERVER",
        status="ACTIVE", resource_id="wlp-callee", raw={},
    )
    ctx = make_ctx(agents=[caller, callee], connections_by_agent={"wlp-caller": [connection]})

    assert ids_for(ctx, RULE_BROKEN_A2A_ID) == []


def test_broken_a2a_delegation_flagged_and_anchored_on_source_agent():
    source = make_agent(id="wlp-caller", name="Caller", status="SUSPENDED", orn="orn:okta:idp:org1:workload-principals:ai-agents:wlp-caller")
    callee = make_agent(id="wlp-callee", name="Callee", status="ACTIVE", orn="orn:okta:idp:org1:workload-principals:ai-agents:wlp-callee")
    delegation = DelegationLinkDTO(
        id="dlk1",
        from_client_orn="orn:okta:idp:org1:workload-principals:ai-agents:wlp-caller",
        to_authorization_server_orn="orn:okta:idp:org1:...:aus1",
        to_resource_orn="orn:okta:idp:org1:workload-principals:ai-agents:wlp-callee",
        raw={},
    )
    ctx = make_ctx(
        agents=[source, callee],
        delegations_by_agent={"wlp-callee": [delegation]},
        agent_orn_to_id={
            "orn:okta:idp:org1:workload-principals:ai-agents:wlp-caller": "wlp-caller",
            "orn:okta:idp:org1:workload-principals:ai-agents:wlp-callee": "wlp-callee",
        },
    )

    assert ids_for(ctx, RULE_BROKEN_A2A_ID) == ["wlp-caller"]


def test_inactive_downstream_app_connection_flagged():
    from app.okta_client.models import DirectoryObjectDTO

    agent = make_agent()
    connection = ConnectionDTO(
        id="mcn1", agent_id="wlp1", connection_type="STS_ACCESS_TOKEN", status="ACTIVE",
        resource_type="APP_INSTANCE", resource_id="app1", raw={},
    )
    apps = {"app1": DirectoryObjectDTO(id="app1", label="Sales App", status="INACTIVE", raw={})}
    ctx = make_ctx(agents=[agent], connections_by_agent={"wlp1": [connection]}, apps=apps)

    assert ids_for(ctx, RULE_INACTIVE_DOWNSTREAM_ID) == ["wlp1"]


def test_inactive_downstream_skips_a2a_connections():
    caller = make_agent(id="wlp-caller", name="Caller", status="ACTIVE")
    callee = make_agent(id="wlp-callee", name="Callee", status="SUSPENDED")
    connection = ConnectionDTO(
        id="mcn1", agent_id="wlp-caller", connection_type="IDENTITY_ASSERTION_A2A_SERVER",
        status="ACTIVE", resource_id="wlp-callee", raw={},
    )
    ctx = make_ctx(agents=[caller, callee], connections_by_agent={"wlp-caller": [connection]})

    assert ids_for(ctx, RULE_INACTIVE_DOWNSTREAM_ID) == []


def test_no_owners_flagged():
    agent = make_agent()
    ctx = make_ctx(agents=[agent])

    assert ids_for(ctx, RULE_NO_OWNERS_ID) == ["wlp1"]


def test_owner_present_not_flagged():
    agent = make_agent(owner_user_ids=["user1"])
    ctx = make_ctx(agents=[agent])

    assert ids_for(ctx, RULE_NO_OWNERS_ID) == []
