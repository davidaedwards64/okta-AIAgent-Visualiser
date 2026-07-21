from datetime import datetime, timedelta, timezone

import httpx

from app.errors import OktaApiError

# Requested scopes for the org authorization server (not a custom AS).
# okta.resourceServers.* / okta.mcpServers.* deliberately omitted: unconfirmed
# scope names for the beta Resource Servers / MCP Servers API surface. See
# README "Verify-live checklist" before adding them.
SCOPES = (
    "openid profile offline_access "
    "okta.users.read okta.groups.read okta.apps.read "
    "okta.authorizationServers.read okta.aiAgents.read"
)


def normalize_org_domain(org_domain: str) -> str:
    domain = org_domain.strip()
    for prefix in ("https://", "http://"):
        if domain.startswith(prefix):
            domain = domain[len(prefix):]
    return domain.rstrip("/")


async def discover(org_domain: str) -> dict:
    """Fetch the org authorization server's OIDC discovery document.
    Using discovery (not hardcoded /oauth2/v1/... paths) so this works across
    okta.com / oktapreview.com / custom-domain orgs without special-casing."""
    url = f"https://{org_domain}/.well-known/openid-configuration"
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(url)
    if resp.status_code != 200:
        raise OktaApiError(resp.status_code, error_summary=f"OIDC discovery failed for {org_domain}")
    return resp.json()


def build_authorize_url(
    authorization_endpoint: str,
    client_id: str,
    redirect_uri: str,
    state: str,
    code_challenge: str,
) -> str:
    params = {
        "response_type": "code",
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "scope": SCOPES,
        "state": state,
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
    }
    query = httpx.QueryParams(params)
    return f"{authorization_endpoint}?{query}"


async def exchange_code_for_tokens(
    token_endpoint: str,
    client_id: str,
    client_secret: str | None,
    code: str,
    redirect_uri: str,
    code_verifier: str,
) -> dict:
    data = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": redirect_uri,
        "client_id": client_id,
        "code_verifier": code_verifier,
    }
    if client_secret:
        data["client_secret"] = client_secret

    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.post(token_endpoint, data=data)

    if resp.status_code != 200:
        raise OktaApiError(resp.status_code, error_summary=f"Token exchange failed: {resp.text}")
    return resp.json()


async def refresh_access_token(
    token_endpoint: str,
    client_id: str,
    client_secret: str | None,
    refresh_token: str,
) -> dict:
    data = {
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
        "client_id": client_id,
    }
    if client_secret:
        data["client_secret"] = client_secret

    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.post(token_endpoint, data=data)

    if resp.status_code != 200:
        raise OktaApiError(resp.status_code, error_summary=f"Token refresh failed: {resp.text}")
    return resp.json()


def token_response_to_expiry(token_response: dict) -> datetime:
    expires_in = token_response.get("expires_in", 3600)
    return datetime.now(timezone.utc) + timedelta(seconds=expires_in)
