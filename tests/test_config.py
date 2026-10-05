import pytest

from app.config import Settings


def test_settings_parse_environment_style_values():
    settings = Settings(
        _env_file=None,
        APP_ENV="test",
        CORS_ORIGINS="https://one.example, https://two.example",
        FIREMAP_URL="https://firemap.example",
    )

    assert settings.cors_origin_list == [
        "https://one.example",
        "https://two.example",
    ]
    assert settings.firemap_url == "https://firemap.example"


def test_runtime_requires_openrouter_key():
    settings = Settings(_env_file=None, APP_ENV="test", OPENROUTER_API_KEY=None)

    with pytest.raises(ValueError, match="OPENROUTER_API_KEY"):
        settings.validate_runtime()


def test_runtime_accepts_minimal_development_config():
    settings = Settings(_env_file=None, APP_ENV="test", OPENROUTER_API_KEY="llm-key")

    settings.validate_runtime()


def test_production_rejects_localhost_cors():
    settings = Settings(
        _env_file=None,
        APP_ENV="production",
        OPENROUTER_API_KEY="llm-key",
        CORS_ORIGINS="http://localhost:5173,https://firesim.cs.gsu.edu",
    )

    with pytest.raises(ValueError, match="localhost"):
        settings.validate_runtime()
