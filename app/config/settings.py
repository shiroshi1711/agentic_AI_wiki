from functools import lru_cache
from pathlib import Path

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


PROJECT_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Telegram
    telegram_bot_token: SecretStr | None = None
    allowed_telegram_user_id: int | None = None

    # Obsidian
    vault_path: Path = Path.home() / "my_obsidian_vault"

    # AI provider
    llm_provider: str = "ollama"
    llm_api_key: SecretStr | None = None
    llm_model: str = ""

    embedding_model: str = "nomic-embed-text"
    
@lru_cache
def get_settings() -> Settings:
    return Settings()
