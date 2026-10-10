"""Validated, environment-backed configuration for the entire service."""

from functools import lru_cache
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Single source of truth for API, agent, and guide settings."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
    )

    app_env: Literal["development", "test", "production"] = Field(
        default="development", alias="APP_ENV"
    )
    host: str = Field(default="0.0.0.0", alias="HOST")
    port: int = Field(default=8000, ge=1, le=65535, alias="PORT")
    api_base_url: str = Field(
        default="http://localhost:8000", alias="API_BASE_URL"
    )
    cors_origins: str = Field(
        default="http://localhost:5173,https://firesim.cs.gsu.edu",
        alias="CORS_ORIGINS",
    )

    openrouter_api_key: str | None = Field(default=None, alias="OPENROUTER_API_KEY")
    openrouter_base_url: str = Field(
        default="https://openrouter.ai/api/v1", alias="OPENROUTER_BASE_URL"
    )
    # OpenRouter model id. Sonnet 5.5 at low effort passed every check in the
    # 12-question comparison at ~$0.008/question; Haiku 4.5 was cheaper but
    # returned an empty answer, and Opus 5.5 cost ~2x with no visible gain.
    llm_model: str = Field(
        default="anthropic/claude-sonnet-5.5", alias="LLM_MODEL"
    )
    llm_max_concurrent_turns: int = Field(
        default=4, ge=1, alias="LLM_MAX_CONCURRENT_TURNS"
    )
    # Per provider request. Without it a hung provider holds a concurrency
    # slot (and the session lock) forever.
    llm_timeout_seconds: float = Field(default=60.0, gt=0, alias="LLM_TIMEOUT_SECONDS")
    llm_max_retries: int = Field(default=2, ge=0, alias="LLM_MAX_RETRIES")
    # Per call, including reasoning tokens. Comparison replies averaged ~350
    # output tokens at low effort; this leaves room without letting one call
    # run up an unbounded bill.
    llm_max_output_tokens: int = Field(default=2048, ge=256, alias="LLM_MAX_OUTPUT_TOKENS")
    # Past exchanges resent with each question. Every one is re-billed on
    # every turn, so this caps how expensive a long session gets.
    llm_history_turns: int = Field(default=6, ge=0, alias="LLM_HISTORY_TURNS")
    # OpenRouter's `reasoning.effort` for models that think (e.g. Sonnet 5.5).
    # "low" cut cost ~25% vs the default with no failed checks; blank = the
    # provider's default.
    llm_reasoning_effort: Literal["low", "medium", "high"] | None = Field(
        default="low", alias="LLM_REASONING_EFFORT"
    )

    @field_validator("llm_reasoning_effort", mode="before")
    @classmethod
    def _blank_effort_is_unset(cls, value):
        return None if value == "" else value

    firemap_url: str = Field(default="http://localhost:5173", alias="FIREMAP_URL")

    @field_validator("cors_origins")
    @classmethod
    def _cors_origins_must_not_be_empty(cls, value: str) -> str:
        if not any(origin.strip() for origin in value.split(",")):
            raise ValueError("CORS_ORIGINS must contain at least one origin")
        return value

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    def validate_runtime(self) -> None:
        """Validate settings required to serve real requests."""
        if not self.openrouter_api_key:
            raise ValueError("OPENROUTER_API_KEY is required")
        if self.app_env == "production":
            localhost_origins = [
                origin
                for origin in self.cors_origin_list
                if "localhost" in origin or "127.0.0.1" in origin
            ]
            if localhost_origins:
                raise ValueError(
                    "Production CORS_ORIGINS must not include localhost origins: "
                    + ", ".join(localhost_origins)
                )


@lru_cache
def get_settings() -> Settings:
    """Return the process-wide immutable settings snapshot."""
    return Settings()


def clear_settings_cache() -> None:
    """Reload environment-backed settings on the next access (primarily tests)."""
    get_settings.cache_clear()
