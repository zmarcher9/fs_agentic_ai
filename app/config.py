"""Application-wide settings loaded from environment variables via Pydantic."""

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Validated configuration for LLM provider, FireMapSim, and runtime environment."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    openai_api_key: str | None = Field(default=None, alias="OPENAI_API_KEY")
    anthropic_api_key: str | None = Field(default=None, alias="ANTHROPIC_API_KEY")
    llm_provider: str = Field(default="openai", alias="LLM_PROVIDER")
    firesim_path: str = Field(..., alias="FIRESIM_PATH")
    app_env: str = Field(default="development", alias="APP_ENV")


@lru_cache
def get_settings() -> Settings:
    """Return cached settings instance loaded from .env."""
    pass  # TODO: return Settings()


def validate_llm_config(settings: Settings) -> None:
    """Ensure the selected LLM provider has required API credentials."""
    pass  # TODO: raise ValueError if provider key is missing
