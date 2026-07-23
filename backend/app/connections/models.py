from pydantic import BaseModel


class SavedConnection(BaseModel):
    """A previously-used org's OIDC app registration, persisted across restarts
    so it doesn't have to be retyped on every connect."""

    org_domain: str
    client_id: str
    client_secret: str | None = None


class SavedConnectionSummary(BaseModel):
    """What the frontend gets for the saved-orgs list — never the secret."""

    org_domain: str
    client_id: str
