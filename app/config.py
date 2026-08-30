from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

API_TITLE = "ULA Monitors API"
API_VERSION = "v1.0.0"
API_DESCRIPTION = Path("app/docs/api_description.md").read_text(encoding="utf-8")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    env: str = "dev"
    mongo_uri: str
    secret_key: str
    admin_username: str
    admin_password: str
    access_token_duration_minutes: int = 480
    cors_origins: str = "*"
    enable_scheduler: bool = False


settings = Settings()  # type: ignore[call-arg]
