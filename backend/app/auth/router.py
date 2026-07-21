from fastapi import APIRouter, Cookie, Depends, HTTPException, Request, Response
from fastapi.responses import RedirectResponse
from pydantic import BaseModel

from app.auth.dependencies import get_session_store
from app.auth.okta_oidc import (
    build_authorize_url,
    discover,
    exchange_code_for_tokens,
    normalize_org_domain,
    token_response_to_expiry,
)
from app.auth.pkce import generate_pkce_pair, generate_state
from app.config import settings
from app.errors import OktaApiError
from app.session.models import SessionData
from app.session.store import SessionStore

router = APIRouter(tags=["auth"])


class LoginRequest(BaseModel):
    org_domain: str
    client_id: str
    client_secret: str | None = None


class LoginResponse(BaseModel):
    authorize_url: str


class MeResponse(BaseModel):
    connected: bool
    org_domain: str | None = None


def _redirect_uri(request: Request) -> str:
    # The SPA is what registers /callback with Okta (redirect URI = {origin}/callback);
    # Vite proxies that path straight to this backend. We derive it from the
    # configured frontend origin rather than request.base_url so it's correct
    # even though the browser never talks to :8000 directly.
    return f"{settings.frontend_origin}/callback"


@router.post("/auth/login", response_model=LoginResponse)
async def login(
    body: LoginRequest,
    request: Request,
    response: Response,
    store: SessionStore = Depends(get_session_store),
) -> LoginResponse:
    org_domain = normalize_org_domain(body.org_domain)

    try:
        discovery = await discover(org_domain)
    except OktaApiError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    verifier, challenge = generate_pkce_pair()
    state = generate_state()

    session_data = SessionData(
        org_domain=org_domain,
        client_id=body.client_id,
        client_secret=body.client_secret,
        pkce_verifier=verifier,
        state=state,
        authorization_endpoint=discovery["authorization_endpoint"],
        token_endpoint=discovery["token_endpoint"],
    )
    session_id = store.create(session_data)

    authorize_url = build_authorize_url(
        discovery["authorization_endpoint"],
        body.client_id,
        _redirect_uri(request),
        state,
        challenge,
    )

    response.set_cookie(
        settings.cookie_name,
        session_id,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
    )
    return LoginResponse(authorize_url=authorize_url)


@router.get("/callback")
async def callback(
    request: Request,
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
    session_id: str | None = Cookie(default=None, alias=settings.cookie_name),
    store: SessionStore = Depends(get_session_store),
) -> RedirectResponse:
    if session_id is None:
        return RedirectResponse(f"{settings.frontend_origin}/?error=no_session")

    data = store.get(session_id)
    if data is None:
        return RedirectResponse(f"{settings.frontend_origin}/?error=no_session")

    if error:
        return RedirectResponse(f"{settings.frontend_origin}/?error={error}")

    if not code or not state or state != data.state:
        return RedirectResponse(f"{settings.frontend_origin}/?error=state_mismatch")

    try:
        token_response = await exchange_code_for_tokens(
            data.token_endpoint,
            data.client_id,
            data.client_secret,
            code,
            _redirect_uri(request),
            data.pkce_verifier,
        )
    except OktaApiError:
        return RedirectResponse(f"{settings.frontend_origin}/?error=token_exchange_failed")

    data.access_token = token_response["access_token"]
    data.refresh_token = token_response.get("refresh_token")
    data.expires_at = token_response_to_expiry(token_response)
    data.pkce_verifier = None
    data.state = None
    store.update(session_id, data)

    return RedirectResponse(f"{settings.frontend_origin}/")


@router.get("/auth/me", response_model=MeResponse)
async def me(
    session_id: str | None = Cookie(default=None, alias=settings.cookie_name),
    store: SessionStore = Depends(get_session_store),
) -> MeResponse:
    if session_id is None:
        return MeResponse(connected=False)
    data = store.get(session_id)
    if data is None or not data.is_connected:
        return MeResponse(connected=False)
    return MeResponse(connected=True, org_domain=data.org_domain)


@router.post("/auth/logout")
async def logout(
    response: Response,
    session_id: str | None = Cookie(default=None, alias=settings.cookie_name),
    store: SessionStore = Depends(get_session_store),
) -> dict:
    if session_id is not None:
        store.delete(session_id)
    response.delete_cookie(settings.cookie_name)
    return {"ok": True}
