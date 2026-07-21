from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """App-level settings only. Org domain / client credentials are entered
    at runtime through the UI and live in the session store, never here."""

    model_config = SettingsConfigDict(env_prefix="OAV_", env_file=".env", extra="ignore")

    port: int = 8000
    frontend_origin: str = "http://localhost:5173"
    cookie_secure: bool = False
    cookie_name: str = "oav_session"


settings = Settings()
