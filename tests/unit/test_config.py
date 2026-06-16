"""AC-17: Settings fail-fast on missing API key / bad db_url."""

import pytest
from pydantic import ValidationError

from data_analyst_agent.config import ConfigError, Settings


def test_settings_defaults_when_api_key_provided(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATA_AGENT_ANTHROPIC_API_KEY", "sk-test")
    s = Settings(db_url="postgresql://u:p@localhost/db")
    assert s.default_model == "claude-sonnet-4-6"
    assert s.max_iterations == 8
    assert s.max_retries == 3  # v3.1: matches 1s/2s/4s backoff
    assert s.llm_timeout_seconds == 60.0
    assert s.statement_timeout_seconds == 10.0
    assert s.row_limit == 1000
    assert s.cache_ttl_seconds == 300
    assert s.min_pool_size == 1
    assert s.max_pool_size == 5
    assert s.enable_redaction is True
    assert s.glossary_path is None
    assert s.otel_endpoint is None
    assert s.log_level == "INFO"


def test_settings_missing_api_key_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DATA_AGENT_ANTHROPIC_API_KEY", raising=False)
    with pytest.raises((ValidationError, ConfigError)) as exc_info:
        Settings(db_url="postgresql://u:p@localhost/db")
    # pydantic reports the field name; the env var is DATA_AGENT_ANTHROPIC_API_KEY
    msg = str(exc_info.value).lower()
    assert "anthropic_api_key" in msg


def test_settings_extra_field_forbidden(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATA_AGENT_ANTHROPIC_API_KEY", "sk-test")
    with pytest.raises(ValidationError):
        Settings(db_url="postgresql://u:p@localhost/db", bogus_field=42)  # type: ignore[call-arg]
