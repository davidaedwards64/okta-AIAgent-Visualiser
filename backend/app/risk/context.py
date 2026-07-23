from dataclasses import dataclass

from app.okta_client.models import (
    AgentDTO,
    ConnectionDTO,
    DelegationLinkDTO,
    DirectoryObjectDTO,
    PolicyRuleGrantDTO,
)


@dataclass
class RiskContext:
    """Everything a RiskRule needs, reusing the exact shapes assemble_graph
    already consumes — no new DTOs. The last three fields are the only data
    fetched specifically for the risk report (never as part of the main
    /api/graph pipeline)."""

    agents: list[AgentDTO]
    connections_by_agent: dict[str, list[ConnectionDTO]]
    delegations_by_agent: dict[str, list[DelegationLinkDTO]]
    agent_orn_to_id: dict[str, str]
    groups: dict[str, DirectoryObjectDTO]
    apps: dict[str, DirectoryObjectDTO]
    auth_servers: dict[str, DirectoryObjectDTO]
    app_groups: dict[str, list[str]]
    auth_server_policy_grants: dict[str, dict[str, list[PolicyRuleGrantDTO]]]
    everyone_group_id: str | None
    org_user_count: int | None
    app_member_user_ids: dict[str, set[str]]
