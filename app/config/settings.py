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
    llm_provider: str = "openai"
    llm_api_key: SecretStr | None = None
    llm_model: str = ""

    embedding_model: str = "nomic-embed-text"

    # Where Ollama is running. Change this in .env when you move to a VPS
    # (OLLAMA_URL=http://...). Before, this address was typed in 3 files.
    ollama_url: str = "http://127.0.0.1:11434"

    # How much text the model can "hold in its head" at once (in tokens).
    # Ollama's default is often only 4096, which is too small once Ella
    # has read a few notes. If your computer struggles, lower this.
    llm_num_ctx: int = 8192

    # Chapter writing
    # Folder INSIDE your vault where approved chapters are saved.
    chapters_folder: str = "Story Building/Chapters"
    # Safety cap on how long one chapter draft may be (in tokens, ~0.75 words each).
    chapter_max_tokens: int = 3500


@lru_cache
def get_settings() -> Settings:
    return Settings()
