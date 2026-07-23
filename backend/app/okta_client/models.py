"""Thin DTOs: only the fields the graph assembly actually consumes.

Deliberately not full Okta schemas. Each `raw` field on the eventual graph
node/edge carries the full source dict for the detail panel, so nothing is
lost by keeping these DTOs narrow.
"""

from pydantic import BaseModel


class AgentDTO(BaseModel):
    id: str
    name: str
    description: str | None = None
    status: str
    platform: str | None = None
    external_id: str | None = None
    linked_app_id: str | None = None
    # Owner shape is UNCONFIRMED against a live tenant (see README verify-live
    # checklist). Populated defensively by ai_agents.py; may be empty even
    # when the agent does have owners if the live shape differs from this guess.
    owner_user_ids: list[str] = []
    owner_group_id: str | None = None
    # orn/provider_id are also best-effort (see ai_agents._parse_agent). orn is
    # required to look up this agent's outbound delegations; when absent that
    # agent is simply skipped from the delegation sweep with a warning.
    orn: str | None = None
    provider_id: str | None = None
    raw: dict


class ConnectionDTO(BaseModel):
    id: str
    agent_id: str
    connection_type: str  # IDENTITY_ASSERTION_CUSTOM_AS | STS_ACCESS_TOKEN | STS_VAULT_SECRET | STS_SERVICE_ACCOUNT
    status: str
    resource_type: str | None = None  # APP_INSTANCE | API_SERVER | MCP_SERVER, only for STS_ACCESS_TOKEN
    resource_id: str | None = None  # appInstanceId | apiServerId | mcpServerId | resource indicator
    resource_indicator: str | None = None
    scope_condition: str | None = None
    scopes: list[str] = []
    authorization_server_id: str | None = None
    raw: dict


class DelegationLinkDTO(BaseModel):
    id: str
    from_client_orn: str
    from_token_type: str | None = None
    to_authorization_server_orn: str
    to_resource_orn: str
    raw: dict


class ProviderDTO(BaseModel):
    id: str
    source_name: str
    source_orn: str | None = None
    # Best-effort, extracted from source_orn (see ai_agents._extract_linked_app_id).
    # When resolved, its Application.label is preferred over source_name for
    # the provider node's display label (source_name is only the generic OIN
    # catalog key, e.g. "amazon_aws_sso", shared by every org using that IdP type).
    linked_app_id: str | None = None
    raw: dict


class PolicyRuleGrantDTO(BaseModel):
    """A single Access Policy Rule match that grants a group access to a
    custom Authorization Server — one per matching rule, so the graph can
    show *why* a group->AuthorizationServer accessPolicy edge exists, not
    just that it does."""

    policy_name: str | None = None
    rule_name: str | None = None
    rule_status: str | None = None
    grant_types: list[str] = []
    scopes: list[str] = []
    raw: dict


class DirectoryObjectDTO(BaseModel):
    """Generic shape for User/Group/App/AuthorizationServer/ResourceServer/MCPServer
    by-id lookups — enough for a node label + detail panel, not the full schema."""

    id: str
    label: str
    status: str | None = None
    sub_label: str | None = None
    raw: dict
