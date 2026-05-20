from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    anthropic_api_key: str
    telegram_bot_token: str
    telegram_chat_id: str

    newsapi_key: str = ""
    market_open_hour: int = 9
    send_offset_minutes: int = 30
    timezone: str = "America/New_York"
    claude_model: str = "claude-opus-4-7"
    log_level: str = "INFO"
    dry_run: bool = False
    db_path: str = "data/history.db"


settings = Settings()
