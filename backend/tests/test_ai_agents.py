from app.okta_client.ai_agents import (
    _extract_linked_app_id,
    _extract_owners,
    _parse_agent,
    _parse_connection,
    _parse_owner_principals,
    _parse_provider,
)


def test_authorization_server_id_extracted_from_self_link():
    """Live tenants return an `authorizationServer` object with no `id` field
    at all — only issuerUrl/name/orn/_links.self.href. Regression test for a
    bug where authorization_server_id was always None, silently breaking both
    the custom-AS connection edge and the AS policy-group lookup (which keys
    off this id)."""
    raw = {
        "id": "mcn10p0o172iDcxZa1d8",
        "connectionType": "IDENTITY_ASSERTION_CUSTOM_AS",
        "status": "ACTIVE",
        "authorizationServer": {
            "issuerUrl": "https://patai.oktapreview.com/oauth2/aus10p0d2l0FMkfz51d8",
            "name": "AS-A2A-InventoryMCP",
            "orn": "orn:oktapreview:idp:00or4k1xtvlY3uTN31d7:authorization_servers:aus10p0d2l0FMkfz51d8",
            "_links": {"self": {"href": "/api/v1/authorizationServers/aus10p0d2l0FMkfz51d8"}},
        },
    }

    connection = _parse_connection(raw, agent_id="wlp10p04q9xHOViFS1d8")

    assert connection.authorization_server_id == "aus10p0d2l0FMkfz51d8"


def test_a2a_target_agent_id_extracted_from_resource_orn():
    """IDENTITY_ASSERTION_A2A_SERVER connections' `resource` has no direct id
    field — the target agent's id is the last segment of its orn."""
    raw = {
        "id": "mcn106h9oz7dRy9IH1d8",
        "connectionType": "IDENTITY_ASSERTION_A2A_SERVER",
        "status": "ACTIVE",
        "scopeCondition": "ALL_SCOPES",
        "scopes": ["*"],
        "resource": {
            "name": "BA: REM Catalog Agent",
            "orn": "orn:oktapreview:directory:00or4k1xtvlY3uTN31d7:resource-servers:a2a:wlp106g1cd3wMMziD1d8",
        },
    }

    connection = _parse_connection(raw, agent_id="wlp106g7tm5uHz0n21d8")

    assert connection.resource_id == "wlp106g1cd3wMMziD1d8"


def test_agent_orn_extracted_from_delegation_links_href():
    """Live tenants return no top-level `orn` on the AI Agent object at all —
    only a delegationLinks href whose filter query embeds the agent's own
    ORN. Regression test for a bug where every agent showed "no ORN
    available, skipped delegation lookup" because of this."""
    raw = {
        "id": "wlp11lqlpqqjGkjaD1d8",
        "status": "ACTIVE",
        "profile": {"name": "DAE OktaMCP Agent"},
        "_links": {
            "self": {"href": "https://patai.oktapreview.com/workload-principals/api/v1/ai-agents/wlp11lqlpqqjGkjaD1d8"},
            "delegationLinks": {
                "href": (
                    "https://patai.oktapreview.com/workload-principals/api/v1/delegation-links"
                    "?filter=to.resourceOrn%20eq%20%22orn:oktapreview:directory:00or4k1xtvlY3uTN31d7"
                    ":workload-principals:ai-agents:wlp11lqlpqqjGkjaD1d8%22"
                )
            },
        },
    }

    agent = _parse_agent(raw)

    assert agent.orn == "orn:oktapreview:directory:00or4k1xtvlY3uTN31d7:workload-principals:ai-agents:wlp11lqlpqqjGkjaD1d8"


def test_provider_id_extracted_from_providers_link_list():
    """Live tenants return `_links.providers` as a *list* of link objects for
    imported agents (e.g. AWS Bedrock), not a single dict. Regression test
    for a bug where isinstance(providers_link, dict) was always False for
    these, so provider_id (and the Provider node/edge) was always None."""
    raw = {
        "id": "wlpzkimar67zJhS1l1d7",
        "status": "STAGED",
        "platform": "AWS_BEDROCK_AGENTS",
        "profile": {"name": "agent-quick-start-7zgx6"},
        "_links": {
            "self": {"href": "https://patai.oktapreview.com/workload-principals/api/v1/ai-agents/wlpzkimar67zJhS1l1d7"},
            "providers": [
                {"href": "https://patai.oktapreview.com/workload-principals/api/v1/ai-agent-providers/aipz4y74buz4Bxs661d7"}
            ],
        },
    }

    agent = _parse_agent(raw)

    assert agent.provider_id == "aipz4y74buz4Bxs661d7"


def test_extract_owners_separates_users_from_group():
    """Confirmed live: the AI Agent object itself has no `owners` field —
    this defensive fallback is only exercised if a different/future tenant
    shape does embed one, modeled as a list of {type, id} refs where at
    most one is a GROUP."""
    raw = {
        "owners": [
            {"type": "USER", "id": "00u1"},
            {"type": "USER", "id": "00u2"},
            {"type": "GROUP", "id": "00g1"},
            {"notAnId": True},
        ]
    }

    user_ids, group_id = _extract_owners(raw)

    assert user_ids == ["00u1", "00u2"]
    assert group_id == "00g1"


def test_extract_owners_empty_when_field_absent():
    assert _extract_owners({"id": "wlp1"}) == ([], None)


def test_parse_owner_principals_from_governance_api_response():
    """Confirmed live shape from GET /governance/api/v1/resource-owners: the
    real user id is only the last orn segment (the top-level `id` is an
    internal principal-ref id, e.g. "pri18j22roUnyTvO41d7", not the user
    id), and `type` is plural ("users")."""
    principals = [
        {
            "id": "pri18j22roUnyTvO41d7",
            "type": "users",
            "orn": "orn:oktapreview:directory:00or4k1xtvlY3uTN31d7:users:00uttth3gaGpYcHfS1d7",
            "profile": {"id": "00uttth3gaGpYcHfS1d7", "name": "David Edwards"},
        }
    ]

    user_ids, group_id = _parse_owner_principals(principals)

    assert user_ids == ["00uttth3gaGpYcHfS1d7"]
    assert group_id is None


def test_parse_owner_principals_recognizes_plural_group_type():
    principals = [{"id": "pri1", "type": "groups", "orn": "orn:oktapreview:directory:org1:groups:00g1"}]

    assert _parse_owner_principals(principals) == ([], "00g1")


def test_parse_owner_principals_empty_list():
    assert _parse_owner_principals([]) == ([], None)


def test_linked_app_id_extracted_from_source_orn():
    """provider.sourceName (e.g. "amazon_aws_sso") is the generic OIN catalog
    key, not this org's admin-assigned app label — the label lives on the
    Application that sourceOrn's embedded app instance id points at. Exact
    orn structure is UNCONFIRMED, so this matches on Okta's well-known "0oa"
    app-instance-id prefix rather than a fixed segment position."""
    source_orn = "orn:oktapreview:directory:00or4k1xtvlY3uTN31d7:apps:0oaabc123XYZ"

    assert _extract_linked_app_id(source_orn) == "0oaabc123XYZ"


def test_linked_app_id_none_when_source_orn_absent_or_unmatched():
    assert _extract_linked_app_id(None) is None
    assert _extract_linked_app_id("orn:oktapreview:directory:00or4k1xtvlY3uTN31d7:idp:00o1") is None


def test_parse_provider_wires_linked_app_id_through():
    raw = {
        "id": "aip1",
        "sourceName": "amazon_aws_sso",
        "sourceOrn": "orn:oktapreview:directory:00or4k1xtvlY3uTN31d7:apps:0oaabc123XYZ",
    }

    provider = _parse_provider(raw)

    assert provider.linked_app_id == "0oaabc123XYZ"
