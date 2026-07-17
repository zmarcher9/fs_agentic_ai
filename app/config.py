"""Validated, environment-backed configuration for the entire service."""

from functools import lru_cache
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Single source of truth for API, agent, geocoder, and browser settings."""

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
    llm_model: str = Field(
        default="anthropic/claude-sonnet-4", alias="LLM_MODEL"
    )
    llm_max_concurrent_turns: int = Field(
        default=4, ge=1, alias="LLM_MAX_CONCURRENT_TURNS"
    )

    geocoder_provider: Literal["nominatim", "mapbox"] = Field(
        default="nominatim", alias="GEOCODER_PROVIDER"
    )
    mapbox_access_token: str | None = Field(default=None, alias="MAPBOX_ACCESS_TOKEN")
    mapbox_permanent: bool = Field(default=True, alias="MAPBOX_PERMANENT")
    nominatim_url: str = Field(
        default="https://nominatim.openstreetmap.org/search",
        alias="NOMINATIM_URL",
    )
    nominatim_user_agent: str = Field(
        default="FireSim-AI/1.0 (+https://firesim.cs.gsu.edu/)",
        alias="NOMINATIM_USER_AGENT",
    )
    geocoder_timeout_seconds: float = Field(
        default=10.0, gt=0, alias="GEOCODER_TIMEOUT_SECONDS"
    )
    geocoder_cache_ttl_seconds: float = Field(
        default=3600.0, ge=0, alias="GEOCODER_CACHE_TTL_SECONDS"
    )
    geocoder_cache_max_entries: int = Field(
        default=500, ge=0, alias="GEOCODER_CACHE_MAX_ENTRIES"
    )

    firemap_url: str = Field(default="http://localhost:5173", alias="FIREMAP_URL")
    playwright_max_contexts: int = Field(
        default=2, ge=1, alias="PLAYWRIGHT_MAX_CONTEXTS"
    )
    playwright_max_waiters: int = Field(
        default=8, ge=0, alias="PLAYWRIGHT_MAX_WAITERS"
    )
    playwright_acquire_timeout_seconds: float = Field(
        default=2.0, gt=0, alias="PLAYWRIGHT_ACQUIRE_TIMEOUT_SECONDS"
    )
    playwright_idle_ttl_seconds: float = Field(
        default=600.0, gt=0, alias="PLAYWRIGHT_IDLE_TTL_SECONDS"
    )

    firesim_path: str | None = Field(default=None, alias="FIRESIM_PATH")

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
        if self.geocoder_provider == "mapbox" and not self.mapbox_access_token:
            raise ValueError(
                "MAPBOX_ACCESS_TOKEN is required when GEOCODER_PROVIDER=mapbox"
            )
        if self.app_env == "production" and self.geocoder_provider != "mapbox":
            raise ValueError("Production deployments must use GEOCODER_PROVIDER=mapbox")
        if self.geocoder_provider == "nominatim":
            normalized_user_agent = self.nominatim_user_agent.casefold()
            placeholders = ("configure", "example.com", "your-team", "changeme")
            if any(value in normalized_user_agent for value in placeholders):
                raise ValueError(
                    "NOMINATIM_USER_AGENT must identify FireSim-AI with a real "
                    "contact URL or email"
                )
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
