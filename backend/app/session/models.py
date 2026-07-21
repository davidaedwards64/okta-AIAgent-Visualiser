from datetime import datetime

from pydantic import BaseModel


class SessionData(BaseModel):
    """Everything held server-side for one connected org session.

    pkce_verifier/state are only populated during the login->callback window
    and are cleared once the callback completes.
    """

    org_domain: str
    client_id: str
    client_secret: str | None = None

    pkce_verifier: str | None = None
    state: str | None = None

    access_token: str | None = None
    refresh_token: str | None = None
    expires_at: datetime | None = None

    authorization_endpoint: str | None = None
    token_endpoint: str | None = None

    @property
    def is_connected(self) -> bool:
        return self.access_token is not None
