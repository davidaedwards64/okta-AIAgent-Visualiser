from datetime import datetime, timedelta, timezone

from fastapi import Cookie, Depends, HTTPException, Request

from app.auth.okta_oidc import refresh_access_token, token_response_to_expiry
from app.config import settings
from app.connections.store import ConnectionsStore
from app.session.models import SessionData
from app.session.store import SessionStore

REFRESH_SKEW = timedelta(minutes=2)


def get_session_store(request: Request) -> SessionStore:
    return request.app.state.session_store


def get_connections_store(request: Request) -> ConnectionsStore:
    return request.app.state.connections_store


async def get_session_data(
    session_id: str | None = Cookie(default=None, alias=settings.cookie_name),
    store: SessionStore = Depends(get_session_store),
) -> tuple[str, SessionData]:
    if session_id is None:
        raise HTTPException(status_code=401, detail="Not connected to an Okta org")
    data = store.get(session_id)
    if data is None or not data.is_connected:
        raise HTTPException(status_code=401, detail="Not connected to an Okta org")
    return session_id, data


async def ensure_valid_token(
    session: tuple[str, SessionData] = Depends(get_session_data),
    store: SessionStore = Depends(get_session_store),
) -> SessionData:
    session_id, data = session

    if data.expires_at and datetime.now(timezone.utc) < (data.expires_at - REFRESH_SKEW):
        return data

    if not data.refresh_token or not data.token_endpoint:
        raise HTTPException(status_code=401, detail="Session expired, please reconnect")

    token_response = await refresh_access_token(
        data.token_endpoint, data.client_id, data.client_secret, data.refresh_token
    )
    data.access_token = token_response["access_token"]
    data.refresh_token = token_response.get("refresh_token", data.refresh_token)
    data.expires_at = token_response_to_expiry(token_response)
    store.update(session_id, data)
    return data
