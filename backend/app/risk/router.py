import asyncio
from datetime import datetime, timezone

from fastapi import APIRouter, Depends

from app.auth.dependencies import ensure_valid_token
from app.errors import OktaApiError
from app.graph.router import GraphFetchContext, _fetch_graph_context
from app.okta_client import directory
from app.okta_client.base import OktaClient
from app.okta_client.models import AgentDTO, ConnectionDTO
from app.risk.context import RiskContext
from app.risk.models import RiskReportResponse
from app.risk.rules import evaluate_risks
from app.session.models import SessionData

router = APIRouter(prefix="/api", tags=["risk"])

CONCURRENCY = 6  # matches graph/router.py's fan-out cap


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


@router.get("/risk-report", response_model=RiskReportResponse)
async def get_risk_report(session: SessionData = Depends(ensure_valid_token)) -> RiskReportResponse:
    """On-demand only, never part of the main /api/graph load. Reuses the
    exact same fetch/resolve pipeline as the graph via _fetch_graph_context,
    then layers on the two pieces only the risk report needs: the Everyone
    group's membership count (org-user-count proxy for rule 3) and, per app,
    the union of its assigned groups' members (also rule 3 only)."""
    client = OktaClient(session.org_domain, session.access_token)

    ctx: GraphFetchContext | None = None
    async for event in _fetch_graph_context(session):
        if event["stage"] == "context":
            ctx = event["context"]
    assert ctx is not None

    warnings = list(ctx.warnings)

    everyone = await directory.find_everyone_group(client)
    everyone_group_id = everyone.id if everyone else None
    org_user_count: int | None = None
    if everyone is not None:
        try:
            org_user_count = len(await directory.list_group_members(client, everyone.id))
        except OktaApiError as exc:
            warnings.append(f"could not fetch Everyone group membership, rule 3 skipped ({exc})")
    else:
        warnings.append("could not find the org's built-in Everyone group; rules 2 and 3 skipped")

    app_member_user_ids: dict[str, set[str]] = {}
    if org_user_count is not None:
        app_ids: set[str] = set()
        for agent in ctx.agents:
            app_ids |= _agent_app_ids(agent, ctx.connections_by_agent.get(agent.id, []))

        sem = asyncio.Semaphore(CONCURRENCY)

        async def fetch_app_member_ids(app_id: str) -> tuple[str, set[str]]:
            member_ids: set[str] = set()

            async def fetch_group(group_id: str) -> None:
                async with sem:
                    try:
                        members = await directory.list_group_members(client, group_id)
                    except OktaApiError as exc:
                        warnings.append(f"group {group_id}: could not fetch members ({exc})")
                        return
                    member_ids.update(m.id for m in members)

            # Excludes the Everyone group deliberately — an app that has Everyone
            # assigned is already flagged by rule 1 (everyone-group-on-app); rule
            # 3 should only fire for a *different* set of groups that happens to
            # cover most of the org, not double-count the same root cause.
            group_ids = [g for g in ctx.app_groups.get(app_id, []) if g != everyone_group_id]
            await asyncio.gather(*(fetch_group(g) for g in group_ids))
            return app_id, member_ids

        results = await asyncio.gather(*(fetch_app_member_ids(app_id) for app_id in app_ids))
        app_member_user_ids = dict(results)

    risk_ctx = RiskContext(
        agents=ctx.agents,
        connections_by_agent=ctx.connections_by_agent,
        delegations_by_agent=ctx.delegations_by_agent,
        agent_orn_to_id=ctx.agent_orn_to_id,
        groups=ctx.groups,
        apps=ctx.apps,
        auth_servers=ctx.auth_servers,
        app_groups=ctx.app_groups,
        auth_server_policy_grants=ctx.auth_server_policy_grants,
        everyone_group_id=everyone_group_id,
        org_user_count=org_user_count,
        app_member_user_ids=app_member_user_ids,
    )

    return RiskReportResponse(
        generated_at=datetime.now(timezone.utc).isoformat(),
        org_domain=session.org_domain,
        findings=evaluate_risks(risk_ctx),
        warnings=warnings,
    )
