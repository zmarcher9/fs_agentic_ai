import pytest

from app.config import Settings


def test_settings_parse_environment_style_values():
    settings = Settings(
        _env_file=None,
        APP_ENV="test",
        CORS_ORIGINS="https://one.example, https://two.example",
        PLAYWRIGHT_MAX_CONTEXTS="4",
        FIREMAP_URL="https://firemap.example",
        GEOCODER_PROVIDER="mapbox",
        MAPBOX_ACCESS_TOKEN="token",
    )

    assert settings.cors_origin_list == [
        "https://one.example",
        "https://two.example",
    ]
    assert settings.playwright_max_contexts == 4
    assert settings.firemap_url == "https://firemap.example"


def test_mapbox_requires_token_at_runtime():
    settings = Settings(
        _env_file=None,
        APP_ENV="test",
        OPENROUTER_API_KEY="llm-key",
        GEOCODER_PROVIDER="mapbox",
        MAPBOX_ACCESS_TOKEN=None,
    )

    with pytest.raises(ValueError, match="MAPBOX_ACCESS_TOKEN"):
        settings.validate_runtime()


def test_nominatim_user_agent_has_real_contact():
    settings = Settings(
        _env_file=None,
        APP_ENV="test",
        OPENROUTER_API_KEY="llm-key",
        GEOCODER_PROVIDER="nominatim",
    )

    settings.validate_runtime()

    assert "https://firesim.cs.gsu.edu/" in settings.nominatim_user_agent


def test_nominatim_rejects_placeholder_contact():
    settings = Settings(
        _env_file=None,
        APP_ENV="test",
        OPENROUTER_API_KEY="llm-key",
        GEOCODER_PROVIDER="nominatim",
        NOMINATIM_USER_AGENT="FireSim-AI/1.0 (contact: your-team@example.com)",
    )

    with pytest.raises(ValueError, match="real contact"):
        settings.validate_runtime()


def test_production_rejects_public_nominatim():
    settings = Settings(
        _env_file=None,
        APP_ENV="production",
        OPENROUTER_API_KEY="llm-key",
        GEOCODER_PROVIDER="nominatim",
        CORS_ORIGINS="https://firesim.cs.gsu.edu",
    )

    with pytest.raises(ValueError, match="Production deployments"):
        settings.validate_runtime()


def test_production_rejects_localhost_cors():
    settings = Settings(
        _env_file=None,
        APP_ENV="production",
        OPENROUTER_API_KEY="llm-key",
        GEOCODER_PROVIDER="mapbox",
        MAPBOX_ACCESS_TOKEN="token",
        CORS_ORIGINS="http://localhost:5173,https://firesim.cs.gsu.edu",
    )

    with pytest.raises(ValueError, match="localhost"):
        settings.validate_runtime()
