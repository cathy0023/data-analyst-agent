"""Settings for data-analyst-agent SDK.

Single source of truth for all tunables. Module-level constants for tunables
are forbidden (RFC DATA-001 Decision #18).
"""

from pathlib import Path

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class ConfigError(Exception):
    """Raised at construction when required config is missing or invalid."""


class Settings(BaseSettings):
    """All SDK tunables. Environment variables use prefix DATA_AGENT_."""

    # Required
    anthropic_api_key: SecretStr
    db_url: str

    # LLM
    default_model: str = "claude-sonnet-4-6"
    max_iterations: int = 8
    llm_timeout_seconds: float = 60.0
    max_retries: int = 3  # matches Error Taxonomy backoff 1s/2s/4s

    # Sandbox / Executor
    statement_timeout_seconds: float = 10.0
    row_limit: int = 1000
    cache_ttl_seconds: int = 300

    # Connection pool
    min_pool_size: int = 1
    max_pool_size: int = 5

    # Redaction (default-on, see §Security)
    enable_redaction: bool = True

    # Business glossary
    glossary_path: Path | None = None

    # Logging
    log_level: str = "INFO"

    # OpenTelemetry (reserved, not implemented)
    otel_endpoint: str | None = None

    model_config = SettingsConfigDict(
        env_prefix="DATA_AGENT_",
        env_file=".env",
        extra="forbid",
    )
