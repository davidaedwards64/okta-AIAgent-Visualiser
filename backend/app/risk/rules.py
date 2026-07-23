"""Extensible risk-rule registry: pure functions, no I/O. Each RiskRule takes
a RiskContext and returns zero or more RiskFindings. Adding a rule later
means writing one `_evaluate_...` function, wrapping it in a RiskRule, and
appending it to RULES — nothing else here needs to change.
"""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal

from app.okta_client.models import AgentDTO, ConnectionDTO
from app.risk.context import RiskContext
from app.risk.models import RiskFinding


@dataclass
class RiskRule:
    id: str
    name: str
    level: Literal["LOW", "MEDIUM", "HIGH"]
    description: str
    evaluate: Callable[[RiskContext], list[RiskFinding]]


def _is_inactive(status: str | None) -> bool:
    """Every status field in this codebase is an opaque Okta passthrough (no
    enum validation anywhere) — treat anything other than ACTIVE as inactive,
    but don't flag None/"UNKNOWN" (agents/connections default to "UNKNOWN"
    when Okta omits status) since "we don't know" isn't the same as "broken".
    UNCONFIRMED against a live tenant — see README checklist."""
    return status is not None and status not in ("ACTIVE", "UNKNOWN")


def _agent_app_ids(agent: AgentDTO, connections: list[ConnectionDTO]) -> set[str]:
    app_ids: set[str] = set()
    if agent.linked_app_id:
        app_ids.add(agent.linked_app_id)
    for connection in connections:
        if (
            connection.connection_type == "STS_ACCESS_TOKEN"
            and connection.resource_type == "APP_INSTANCE"
            and connection.resource_id
        ):
            app_ids.add(connection.resource_id)
    return app_ids


def _app_label(ctx: RiskContext, app_id: str) -> str:
    app = ctx.apps.get(app_id)
    return app.label if app else app_id


def _evaluate_everyone_on_app(ctx: RiskContext) -> list[RiskFinding]:
    if not ctx.everyone_group_id:
        return []
    findings = []
    for agent in ctx.agents:
        connections = ctx.connections_by_agent.get(agent.id, [])
        for app_id in _agent_app_ids(agent, connections):
            if ctx.everyone_group_id in ctx.app_groups.get(app_id, []):
                findings.append(
                    RiskFinding(
                        rule_id=RULE_EVERYONE_ON_APP_ID,
                        rule_name=RULE_EVERYONE_ON_APP_NAME,
                        level="HIGH",
                        description=RULE_EVERYONE_ON_APP_DESCRIPTION,
                        agent_id=agent.id,
                        agent_name=agent.name,
                        detail=f"The Everyone group is assigned to app '{_app_label(ctx, app_id)}', which this agent uses.",
                    )
                )
    return findings


def _evaluate_everyone_on_policy(ctx: RiskContext) -> list[RiskFinding]:
    if not ctx.everyone_group_id:
        return []
    findings = []
    for agent in ctx.agents:
        connections = ctx.connections_by_agent.get(agent.id, [])
        auth_server_ids = {
            c.authorization_server_id
            for c in connections
            if c.connection_type == "IDENTITY_ASSERTION_CUSTOM_AS" and c.authorization_server_id
        }
        for auth_server_id in auth_server_ids:
            if ctx.everyone_group_id in ctx.auth_server_policy_grants.get(auth_server_id, {}):
                auth_server = ctx.auth_servers.get(auth_server_id)
                label = auth_server.label if auth_server else auth_server_id
                findings.append(
                    RiskFinding(
                        rule_id=RULE_EVERYONE_ON_POLICY_ID,
                        rule_name=RULE_EVERYONE_ON_POLICY_NAME,
                        level="LOW",
                        description=RULE_EVERYONE_ON_POLICY_DESCRIPTION,
                        agent_id=agent.id,
                        agent_name=agent.name,
                        detail=f"The Everyone group has an Access Policy Rule grant on custom authorization "
                        f"server '{label}', which this agent uses.",
                    )
                )
    return findings


def _evaluate_high_pct_users(ctx: RiskContext) -> list[RiskFinding]:
    if not ctx.org_user_count:
        return []
    findings = []
    for agent in ctx.agents:
        connections = ctx.connections_by_agent.get(agent.id, [])
        for app_id in _agent_app_ids(agent, connections):
            member_ids = ctx.app_member_user_ids.get(app_id)
            if not member_ids:
                continue
            pct = len(member_ids) / ctx.org_user_count
            if pct > 0.8:
                findings.append(
                    RiskFinding(
                        rule_id=RULE_HIGH_PCT_USERS_ID,
                        rule_name=RULE_HIGH_PCT_USERS_NAME,
                        level="MEDIUM",
                        description=RULE_HIGH_PCT_USERS_DESCRIPTION,
                        agent_id=agent.id,
                        agent_name=agent.name,
                        detail=f"{len(member_ids)} of {ctx.org_user_count} org users ({pct:.0%}) are assigned to "
                        f"app '{_app_label(ctx, app_id)}', which this agent uses.",
                    )
                )
    return findings


def _evaluate_secrets_or_service_accounts(ctx: RiskContext) -> list[RiskFinding]:
    findings = []
    for agent in ctx.agents:
        connections = ctx.connections_by_agent.get(agent.id, [])
        offending = [c for c in connections if c.connection_type in ("STS_VAULT_SECRET", "STS_SERVICE_ACCOUNT")]
        if not offending:
            continue
        kinds = sorted({"secret" if c.connection_type == "STS_VAULT_SECRET" else "service account" for c in offending})
        findings.append(
            RiskFinding(
                rule_id=RULE_SECRETS_OR_SERVICE_ACCOUNTS_ID,
                rule_name=RULE_SECRETS_OR_SERVICE_ACCOUNTS_NAME,
                level="LOW",
                description=RULE_SECRETS_OR_SERVICE_ACCOUNTS_DESCRIPTION,
                agent_id=agent.id,
                agent_name=agent.name,
                detail=f"Uses {len(offending)} {'/'.join(kinds)} connection(s).",
            )
        )
    return findings


def _evaluate_broken_a2a(ctx: RiskContext) -> list[RiskFinding]:
    agents_by_id = {a.id: a for a in ctx.agents}

    # Collect every broken A2A link first, as (source, target, via), then
    # group by whichever single agent is actually inactive. One broken
    # agent that fans out/in to several counterparts should read as ONE
    # finding anchored on that agent — not one finding per counterpart,
    # scattered across otherwise-healthy agents that merely reference it.
    links: list[tuple[AgentDTO, AgentDTO, str]] = []
    for agent in ctx.agents:
        for connection in ctx.connections_by_agent.get(agent.id, []):
            if connection.connection_type != "IDENTITY_ASSERTION_A2A_SERVER":
                continue
            target = agents_by_id.get(connection.resource_id) if connection.resource_id else None
            if target is None:
                continue
            if _is_inactive(connection.status) or _is_inactive(agent.status) or _is_inactive(target.status):
                links.append((agent, target, "connection"))

        for delegation in ctx.delegations_by_agent.get(agent.id, []):
            source_id = ctx.agent_orn_to_id.get(delegation.from_client_orn)
            source = agents_by_id.get(source_id) if source_id else None
            if source is None:
                continue
            if _is_inactive(source.status) or _is_inactive(agent.status):
                links.append((source, agent, "delegation"))

    by_anchor: dict[str, tuple[AgentDTO, set[str]]] = {}
    for source, target, via in links:
        if _is_inactive(target.status):
            # Target is the broken one — anchor there, note the caller.
            anchor, note = target, f"incoming {via} from '{source.name}'"
        else:
            # Either the source is inactive, or neither agent is (only the
            # link itself is) — anchor on the source, as before.
            anchor, note = source, f"outgoing {via} to '{target.name}'"
        _, notes = by_anchor.setdefault(anchor.id, (anchor, set()))
        notes.add(note)

    findings = []
    for anchor, notes in by_anchor.values():
        sorted_notes = sorted(notes)
        findings.append(
            RiskFinding(
                rule_id=RULE_BROKEN_A2A_ID,
                rule_name=RULE_BROKEN_A2A_NAME,
                level="MEDIUM",
                description=RULE_BROKEN_A2A_DESCRIPTION,
                agent_id=anchor.id,
                agent_name=anchor.name,
                detail=(
                    f"{len(sorted_notes)} broken agent-to-agent link(s) (agent or link inactive): "
                    + "; ".join(sorted_notes)
                ),
            )
        )
    return findings


def _downstream_target_status(ctx: RiskContext, connection: ConnectionDTO) -> str | None:
    """Status of the resolved target object, when that object type carries
    one (see assemble.py::_resolve_connection_target — resourceServer/
    mcpServer nodes have no status field at all)."""
    if connection.connection_type == "STS_ACCESS_TOKEN" and connection.resource_type == "APP_INSTANCE":
        app = ctx.apps.get(connection.resource_id) if connection.resource_id else None
        return app.status if app else None
    if connection.connection_type == "IDENTITY_ASSERTION_CUSTOM_AS":
        auth_server = ctx.auth_servers.get(connection.authorization_server_id) if connection.authorization_server_id else None
        return auth_server.status if auth_server else None
    return None


def _evaluate_inactive_downstream(ctx: RiskContext) -> list[RiskFinding]:
    findings = []
    for agent in ctx.agents:
        for connection in ctx.connections_by_agent.get(agent.id, []):
            if connection.connection_type == "IDENTITY_ASSERTION_A2A_SERVER":
                continue  # covered by rule 5
            if _is_inactive(connection.status) or _is_inactive(_downstream_target_status(ctx, connection)):
                findings.append(
                    RiskFinding(
                        rule_id=RULE_INACTIVE_DOWNSTREAM_ID,
                        rule_name=RULE_INACTIVE_DOWNSTREAM_NAME,
                        level="LOW",
                        description=RULE_INACTIVE_DOWNSTREAM_DESCRIPTION,
                        agent_id=agent.id,
                        agent_name=agent.name,
                        detail=f"Connection '{connection.id}' ({connection.connection_type}) or its target is inactive.",
                    )
                )
    return findings


def _evaluate_no_owners(ctx: RiskContext) -> list[RiskFinding]:
    return [
        RiskFinding(
            rule_id=RULE_NO_OWNERS_ID,
            rule_name=RULE_NO_OWNERS_NAME,
            level="LOW",
            description=RULE_NO_OWNERS_DESCRIPTION,
            agent_id=agent.id,
            agent_name=agent.name,
            detail="No owner users or owner group are assigned to this agent.",
        )
        for agent in ctx.agents
        if not agent.owner_user_ids and not agent.owner_group_id
    ]


def _evaluate_inactive_owner(ctx: RiskContext) -> list[RiskFinding]:
    findings = []
    for agent in ctx.agents:
        inactive_owners = sorted(
            {
                ctx.users[uid].label or uid
                for uid in agent.owner_user_ids
                if ctx.users.get(uid) and _is_inactive(ctx.users[uid].status)
            }
        )
        if inactive_owners:
            findings.append(
                RiskFinding(
                    rule_id=RULE_INACTIVE_OWNER_ID,
                    rule_name=RULE_INACTIVE_OWNER_NAME,
                    level="MEDIUM",
                    description=RULE_INACTIVE_OWNER_DESCRIPTION,
                    agent_id=agent.id,
                    agent_name=agent.name,
                    detail=f"Owner(s) no longer active: {', '.join(inactive_owners)}.",
                )
            )
    return findings


def _evaluate_shared_credential(ctx: RiskContext) -> list[RiskFinding]:
    agents_by_id = {a.id: a for a in ctx.agents}

    # Same consolidation shape as _evaluate_broken_a2a: find every group of
    # agents sharing an indicator first, then emit one finding per agent
    # naming the others in its group.
    by_indicator: dict[str, set[str]] = {}
    for agent_id, connections in ctx.connections_by_agent.items():
        for connection in connections:
            if connection.connection_type not in ("STS_VAULT_SECRET", "STS_SERVICE_ACCOUNT"):
                continue
            if not connection.resource_indicator:
                continue  # can't prove sharing without an identifier — see README checklist
            by_indicator.setdefault(connection.resource_indicator, set()).add(agent_id)

    findings = []
    for agent_ids in by_indicator.values():
        if len(agent_ids) < 2:
            continue
        for agent_id in agent_ids:
            agent = agents_by_id.get(agent_id)
            if agent is None:
                continue
            others = sorted(agents_by_id[other].name for other in agent_ids if other != agent_id and other in agents_by_id)
            if not others:
                continue
            findings.append(
                RiskFinding(
                    rule_id=RULE_SHARED_CREDENTIAL_ID,
                    rule_name=RULE_SHARED_CREDENTIAL_NAME,
                    level="MEDIUM",
                    description=RULE_SHARED_CREDENTIAL_DESCRIPTION,
                    agent_id=agent.id,
                    agent_name=agent.name,
                    detail=f"Shares a vaulted secret/service-account credential with: {', '.join(others)}.",
                )
            )
    return findings


SENSITIVE_SCOPE_KEYWORDS = ("admin", "manage", "superuser")


def _is_sensitive_scope(scope: str) -> bool:
    """Heuristic only, not an Okta-defined scope taxonomy — Okta doesn't tag
    scopes as sensitive anywhere in this API surface. Tune this keyword list
    to your own org's scope-naming conventions."""
    if scope == "*":
        return True
    lowered = scope.lower()
    return lowered.endswith("write") or any(keyword in lowered for keyword in SENSITIVE_SCOPE_KEYWORDS)


def _agent_own_scopes(ctx: RiskContext, agent_id: str) -> set[str]:
    scopes: set[str] = set()
    for connection in ctx.connections_by_agent.get(agent_id, []):
        scopes.update(connection.scopes)
    return scopes


def _evaluate_sensitive_scopes(ctx: RiskContext) -> list[RiskFinding]:
    findings = []
    for agent in ctx.agents:
        sensitive = sorted({s for s in _agent_own_scopes(ctx, agent.id) if _is_sensitive_scope(s)})
        if sensitive:
            findings.append(
                RiskFinding(
                    rule_id=RULE_SENSITIVE_SCOPES_ID,
                    rule_name=RULE_SENSITIVE_SCOPES_NAME,
                    level="HIGH",
                    description=RULE_SENSITIVE_SCOPES_DESCRIPTION,
                    agent_id=agent.id,
                    agent_name=agent.name,
                    detail=f"Holds broad/sensitive scope(s): {', '.join(sensitive)}.",
                )
            )
    return findings


def _active_a2a_edges(ctx: RiskContext) -> list[tuple[str, str]]:
    """(source_agent_id, target_agent_id) pairs for every ACTIVE-only A2A
    connection or delegation link — the same links _evaluate_broken_a2a
    flags as broken are excluded here, since a cycle or an escalation path
    only matters if the whole loop/hop is actually live."""
    agents_by_id = {a.id: a for a in ctx.agents}
    edges: list[tuple[str, str]] = []
    for agent in ctx.agents:
        for connection in ctx.connections_by_agent.get(agent.id, []):
            if connection.connection_type != "IDENTITY_ASSERTION_A2A_SERVER":
                continue
            target = agents_by_id.get(connection.resource_id) if connection.resource_id else None
            if target is None:
                continue
            if _is_inactive(connection.status) or _is_inactive(agent.status) or _is_inactive(target.status):
                continue
            edges.append((agent.id, target.id))

        for delegation in ctx.delegations_by_agent.get(agent.id, []):
            source_id = ctx.agent_orn_to_id.get(delegation.from_client_orn)
            source = agents_by_id.get(source_id) if source_id else None
            if source is None:
                continue
            if _is_inactive(source.status) or _is_inactive(agent.status):
                continue
            edges.append((source.id, agent.id))
    return edges


def _evaluate_delegation_cycle(ctx: RiskContext) -> list[RiskFinding]:
    agents_by_id = {a.id: a for a in ctx.agents}
    adjacency: dict[str, set[str]] = {}
    for source_id, target_id in _active_a2a_edges(ctx):
        adjacency.setdefault(source_id, set()).add(target_id)

    def reachable_from(start: str) -> set[str]:
        seen: set[str] = set()
        stack = list(adjacency.get(start, ()))
        while stack:
            node = stack.pop()
            if node in seen:
                continue
            seen.add(node)
            stack.extend(adjacency.get(node, ()))
        return seen

    findings = []
    for agent_id in adjacency:
        downstream = reachable_from(agent_id)
        if agent_id not in downstream:
            continue  # no path back to itself -> not on a cycle
        agent = agents_by_id.get(agent_id)
        if agent is None:
            continue
        cycle_peers = sorted(
            agents_by_id[n].name for n in downstream if n != agent_id and n in agents_by_id and agent_id in reachable_from(n)
        )
        detail = (
            f"On a circular delegation chain with: {', '.join(cycle_peers)}."
            if cycle_peers
            else "Delegates back to itself in a self-referential A2A loop."
        )
        findings.append(
            RiskFinding(
                rule_id=RULE_DELEGATION_CYCLE_ID,
                rule_name=RULE_DELEGATION_CYCLE_NAME,
                level="MEDIUM",
                description=RULE_DELEGATION_CYCLE_DESCRIPTION,
                agent_id=agent.id,
                agent_name=agent.name,
                detail=detail,
            )
        )
    return findings


FANOUT_THRESHOLD = 8


def _evaluate_high_fanout(ctx: RiskContext) -> list[RiskFinding]:
    findings = []
    for agent in ctx.agents:
        targets: set[tuple[str, str]] = set()
        for connection in ctx.connections_by_agent.get(agent.id, []):
            if connection.connection_type == "IDENTITY_ASSERTION_A2A_SERVER":
                continue  # fan-out to other agents is covered by its own risk shape, not blast radius
            identifier = connection.resource_id or connection.resource_indicator or connection.authorization_server_id
            if identifier is None:
                continue
            targets.add((connection.connection_type, identifier))
        if len(targets) > FANOUT_THRESHOLD:
            findings.append(
                RiskFinding(
                    rule_id=RULE_HIGH_FANOUT_ID,
                    rule_name=RULE_HIGH_FANOUT_NAME,
                    level="LOW",
                    description=RULE_HIGH_FANOUT_DESCRIPTION,
                    agent_id=agent.id,
                    agent_name=agent.name,
                    detail=f"Connects to {len(targets)} distinct downstream resources (threshold: {FANOUT_THRESHOLD}).",
                )
            )
    return findings


def _evaluate_delegation_privilege_escalation(ctx: RiskContext) -> list[RiskFinding]:
    agents_by_id = {a.id: a for a in ctx.agents}
    by_callee: dict[str, tuple[AgentDTO, set[str]]] = {}
    for source_id, target_id in _active_a2a_edges(ctx):
        caller_scopes = _agent_own_scopes(ctx, source_id)
        callee_sensitive = {s for s in _agent_own_scopes(ctx, target_id) if _is_sensitive_scope(s)}
        gap = sorted(callee_sensitive - caller_scopes)
        if not gap:
            continue
        caller = agents_by_id.get(source_id)
        callee = agents_by_id.get(target_id)
        if caller is None or callee is None:
            continue
        _, notes = by_callee.setdefault(callee.id, (callee, set()))
        notes.add(f"{caller.name} (missing: {', '.join(gap)})")

    return [
        RiskFinding(
            rule_id=RULE_DELEGATION_PRIVILEGE_ESCALATION_ID,
            rule_name=RULE_DELEGATION_PRIVILEGE_ESCALATION_NAME,
            level="HIGH",
            description=RULE_DELEGATION_PRIVILEGE_ESCALATION_DESCRIPTION,
            agent_id=callee.id,
            agent_name=callee.name,
            detail="Reachable via delegation from lower-privileged caller(s): " + "; ".join(sorted(notes)),
        )
        for callee, notes in by_callee.values()
    ]


RULE_EVERYONE_ON_APP_ID = "everyone-group-on-app"
RULE_EVERYONE_ON_APP_NAME = "Everyone group assigned to AI Agent App"
RULE_EVERYONE_ON_APP_DESCRIPTION = (
    "The Okta built-in 'Everyone' group is assigned to the application linked to this agent (either "
    "its user sign-on app, or an app it holds an STS access-token connection to), meaning every user "
    "in the org can access it. Determine by: the Everyone group appears in the assigned-groups list "
    "of an application this agent uses."
)

RULE_EVERYONE_ON_POLICY_ID = "everyone-group-on-policy"
RULE_EVERYONE_ON_POLICY_NAME = "Everyone group assigned to CAS Access Policy Rule"
RULE_EVERYONE_ON_POLICY_DESCRIPTION = (
    "The Okta built-in 'Everyone' group has a grant on an Access Policy Rule of a custom "
    "Authorization Server this agent connects to, meaning every user in the org is covered by that "
    "policy rule. Determine by: the Everyone group appears as a policy-rule grant on a custom "
    "authorization server this agent uses."
)

RULE_HIGH_PCT_USERS_ID = "high-pct-org-users"
RULE_HIGH_PCT_USERS_NAME = "High %age of Users Assigned to AI Agent"
RULE_HIGH_PCT_USERS_DESCRIPTION = (
    "More than 80% of the org's users are assigned to an application this agent uses, approximated "
    "using the Okta built-in 'Everyone' group's membership count as the org user-count denominator. "
    "Determine by: (members of the app's assigned groups) / (Everyone group membership) > 80%."
)

RULE_SECRETS_OR_SERVICE_ACCOUNTS_ID = "secrets-or-service-accounts"
RULE_SECRETS_OR_SERVICE_ACCOUNTS_NAME = "Agent using secrets or service accounts"
RULE_SECRETS_OR_SERVICE_ACCOUNTS_DESCRIPTION = (
    "This agent has a resource connection to a vaulted secret or a privileged service account, which "
    "typically carries broader/standing access than a scoped, agent-specific credential. Determine "
    "by: the agent has a connection of type STS_VAULT_SECRET or STS_SERVICE_ACCOUNT."
)

RULE_BROKEN_A2A_ID = "broken-a2a"
RULE_BROKEN_A2A_NAME = "Broken Agent2Agent Connections"
RULE_BROKEN_A2A_DESCRIPTION = (
    "This agent has an agent-to-agent (A2A) connection or delegation link where either agent, or the "
    "connection itself, is not ACTIVE — the delegation is effectively broken. Determine by: an "
    "IDENTITY_ASSERTION_A2A_SERVER connection/delegation where the connection status, source agent "
    "status, or target agent status is inactive."
)

RULE_INACTIVE_DOWNSTREAM_ID = "inactive-downstream"
RULE_INACTIVE_DOWNSTREAM_NAME = "Inactive Downstream Components"
RULE_INACTIVE_DOWNSTREAM_DESCRIPTION = (
    "This agent has a non-agent resource connection (application, authorization server, secret, "
    "service account, resource/MCP server) where the connection or the resolved target is not "
    "ACTIVE. Determine by: any non-A2A connection whose own status, or resolved target's status, is "
    "inactive."
)

RULE_NO_OWNERS_ID = "no-owners"
RULE_NO_OWNERS_NAME = "No Owners Assigned"
RULE_NO_OWNERS_DESCRIPTION = (
    "This agent has no owner users and no owner group assigned, so there's no clear accountable "
    "party for its access. Determine by: the agent's owner_user_ids list is empty and owner_group_id "
    "is unset."
)

RULE_INACTIVE_OWNER_ID = "inactive-owner"
RULE_INACTIVE_OWNER_NAME = "Owner No Longer Active"
RULE_INACTIVE_OWNER_DESCRIPTION = (
    "This agent has an owner on record, but that owner's Okta user account is not ACTIVE "
    "(deprovisioned, suspended, etc.), so the accountable party for this agent's access no longer "
    "exists in any meaningful sense. Determine by: any id in the agent's owner_user_ids resolves to "
    "a user whose status is inactive."
)

RULE_SHARED_CREDENTIAL_ID = "shared-credential"
RULE_SHARED_CREDENTIAL_NAME = "Shared Secret or Service Account Credential"
RULE_SHARED_CREDENTIAL_DESCRIPTION = (
    "This agent's vaulted-secret or service-account connection points at the same underlying "
    "credential as another agent, so a single leaked or compromised credential has blast radius "
    "across multiple agents at once. Determine by: two or more agents have an STS_VAULT_SECRET or "
    "STS_SERVICE_ACCOUNT connection sharing the same resource indicator."
)

RULE_SENSITIVE_SCOPES_ID = "sensitive-scope-grant"
RULE_SENSITIVE_SCOPES_NAME = "Overly Broad or Sensitive Scope Grant"
RULE_SENSITIVE_SCOPES_DESCRIPTION = (
    "This agent holds a wildcard scope or a scope matching a sensitive-keyword heuristic (admin, "
    "manage, superuser, or a trailing 'write'), which is broader access than most agent use cases "
    "need. This keyword list is a heuristic, not an Okta-defined scope taxonomy — tune it to your "
    "org's own scope-naming conventions. Determine by: any scope on any of the agent's connections "
    "is '*' or matches the sensitive-keyword list."
)

RULE_DELEGATION_CYCLE_ID = "delegation-cycle"
RULE_DELEGATION_CYCLE_NAME = "Circular Agent Delegation"
RULE_DELEGATION_CYCLE_DESCRIPTION = (
    "This agent sits on a circular chain of active agent-to-agent connections or delegation links "
    "(A calls B calls ... calls A), which can produce confused-deputy access paths or runaway "
    "delegation loops. Determine by: the agent can reach itself by following only ACTIVE "
    "IDENTITY_ASSERTION_A2A_SERVER connections and delegation links."
)

RULE_HIGH_FANOUT_ID = "high-fanout"
RULE_HIGH_FANOUT_NAME = "High Fan-Out (Blast Radius) Agent"
RULE_HIGH_FANOUT_DESCRIPTION = (
    f"This agent has an unusually large number of distinct downstream resource connections (more "
    f"than {FANOUT_THRESHOLD}), making it a high-value target — compromising it exposes many "
    f"systems at once. The threshold is a tunable heuristic, not an Okta-defined limit. Determine "
    f"by: the agent has more than {FANOUT_THRESHOLD} distinct non-A2A (connection_type, target) pairs."
)

RULE_DELEGATION_PRIVILEGE_ESCALATION_ID = "delegation-privilege-escalation"
RULE_DELEGATION_PRIVILEGE_ESCALATION_NAME = "Privilege Escalation via Delegation"
RULE_DELEGATION_PRIVILEGE_ESCALATION_DESCRIPTION = (
    "This agent can be reached via an active agent-to-agent connection or delegation link from a "
    "caller that itself lacks one or more of this agent's sensitive scopes — a lower-privileged "
    "agent can effectively borrow this agent's broader access one hop away. This is the most "
    "speculative rule of the set: scope location per connection type is UNCONFIRMED against a live "
    "tenant. Determine by: a caller's aggregate connection scopes are missing a sensitive scope this "
    "agent holds, and the two are linked by an ACTIVE A2A connection or delegation."
)

RULES: list[RiskRule] = [
    RiskRule(RULE_EVERYONE_ON_APP_ID, RULE_EVERYONE_ON_APP_NAME, "HIGH", RULE_EVERYONE_ON_APP_DESCRIPTION, _evaluate_everyone_on_app),
    RiskRule(RULE_EVERYONE_ON_POLICY_ID, RULE_EVERYONE_ON_POLICY_NAME, "LOW", RULE_EVERYONE_ON_POLICY_DESCRIPTION, _evaluate_everyone_on_policy),
    RiskRule(RULE_HIGH_PCT_USERS_ID, RULE_HIGH_PCT_USERS_NAME, "MEDIUM", RULE_HIGH_PCT_USERS_DESCRIPTION, _evaluate_high_pct_users),
    RiskRule(
        RULE_SECRETS_OR_SERVICE_ACCOUNTS_ID,
        RULE_SECRETS_OR_SERVICE_ACCOUNTS_NAME,
        "LOW",
        RULE_SECRETS_OR_SERVICE_ACCOUNTS_DESCRIPTION,
        _evaluate_secrets_or_service_accounts,
    ),
    RiskRule(RULE_BROKEN_A2A_ID, RULE_BROKEN_A2A_NAME, "MEDIUM", RULE_BROKEN_A2A_DESCRIPTION, _evaluate_broken_a2a),
    RiskRule(RULE_INACTIVE_DOWNSTREAM_ID, RULE_INACTIVE_DOWNSTREAM_NAME, "LOW", RULE_INACTIVE_DOWNSTREAM_DESCRIPTION, _evaluate_inactive_downstream),
    RiskRule(RULE_NO_OWNERS_ID, RULE_NO_OWNERS_NAME, "LOW", RULE_NO_OWNERS_DESCRIPTION, _evaluate_no_owners),
    RiskRule(RULE_INACTIVE_OWNER_ID, RULE_INACTIVE_OWNER_NAME, "MEDIUM", RULE_INACTIVE_OWNER_DESCRIPTION, _evaluate_inactive_owner),
    RiskRule(RULE_SHARED_CREDENTIAL_ID, RULE_SHARED_CREDENTIAL_NAME, "MEDIUM", RULE_SHARED_CREDENTIAL_DESCRIPTION, _evaluate_shared_credential),
    RiskRule(RULE_SENSITIVE_SCOPES_ID, RULE_SENSITIVE_SCOPES_NAME, "HIGH", RULE_SENSITIVE_SCOPES_DESCRIPTION, _evaluate_sensitive_scopes),
    RiskRule(RULE_DELEGATION_CYCLE_ID, RULE_DELEGATION_CYCLE_NAME, "MEDIUM", RULE_DELEGATION_CYCLE_DESCRIPTION, _evaluate_delegation_cycle),
    RiskRule(RULE_HIGH_FANOUT_ID, RULE_HIGH_FANOUT_NAME, "LOW", RULE_HIGH_FANOUT_DESCRIPTION, _evaluate_high_fanout),
    RiskRule(
        RULE_DELEGATION_PRIVILEGE_ESCALATION_ID,
        RULE_DELEGATION_PRIVILEGE_ESCALATION_NAME,
        "HIGH",
        RULE_DELEGATION_PRIVILEGE_ESCALATION_DESCRIPTION,
        _evaluate_delegation_privilege_escalation,
    ),
]


def evaluate_risks(ctx: RiskContext) -> list[RiskFinding]:
    return [finding for rule in RULES for finding in rule.evaluate(ctx)]
