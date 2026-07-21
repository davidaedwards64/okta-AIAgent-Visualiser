"""Per-type "Open in Okta" Admin Console URL builder.

Patterns for user/group/application/authorizationServer are Okta's
longstanding, documented Admin Console conventions. Patterns for
agent/resourceServer/mcpServer are genuinely new (beta) UI with nothing
documented anywhere checked during planning — those three deliberately
return None so the frontend can render "Open in Okta" disabled rather than
linking to a guessed, possibly-wrong URL. See README "Verify-live checklist"
item 3: hand-navigate the real Admin Console once and fill these in.
"""

from app.graph.contract import NodeType


def _admin_host(org_domain: str) -> str:
    """Assumes org_domain is the org's native *.okta.com / *.oktapreview.com
    domain. If the org uses a vanity custom domain, this derivation is wrong
    — see README "Verify-live checklist" item 5."""
    if ".oktapreview.com" in org_domain:
        base = org_domain.replace(".oktapreview.com", "")
        return f"{base}-admin.oktapreview.com"
    if ".okta.com" in org_domain:
        base = org_domain.replace(".okta.com", "")
        return f"{base}-admin.okta.com"
    return org_domain


def build_admin_url(
    org_domain: str,
    node_type: NodeType,
    okta_id: str,
    app_catalog_key: str | None = None,
) -> str | None:
    host = _admin_host(org_domain)

    if node_type == "user":
        return f"https://{host}/admin/user/profile/view/{okta_id}"
    if node_type == "group":
        return f"https://{host}/admin/group/{okta_id}"
    if node_type == "application":
        key = app_catalog_key or "oidc_client"
        return f"https://{host}/admin/app/{key}/instance/{okta_id}#tab-general"
    if node_type == "authorizationServer":
        return f"https://{host}/admin/oauth2/as/{okta_id}"

    # agent, resourceServer, mcpServer, secret, serviceAccount, provider:
    # no confirmed Admin Console URL pattern yet.
    return None
