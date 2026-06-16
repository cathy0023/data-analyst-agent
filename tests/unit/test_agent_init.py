"""AC-17 + thread-safety contract: DataAnalyst.__init__ fail-fast + close idempotency."""

import asyncio

import pytest

from data_analyst_agent import Answer, AskError, DataAnalyst, TokenUsage
from data_analyst_agent.config import ConfigError


def test_public_api_imports_resolve() -> None:
    """AC-2: from data_analyst_agent import DataAnalyst, Answer, AskError, TokenUsage."""
    assert DataAnalyst is not None
    assert Answer is not None
    assert AskError is not None
    assert TokenUsage is not None


def test_init_fails_without_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    """AC-17: missing ANTHROPIC_API_KEY raises at __init__ time."""
    monkeypatch.delenv("DATA_AGENT_ANTHROPIC_API_KEY", raising=False)
    with pytest.raises((ConfigError, Exception)) as exc_info:
        DataAnalyst(db_url="postgresql://u:p@localhost/db")
    assert "ANTHROPIC_API_KEY" in str(exc_info.value)


def test_init_with_settings_does_not_connect_yet(
    monkeypatch: pytest.MonkeyPatch, seeded_db_url: str
) -> None:
    """W1 contract: __init__ takes settings, does not eagerly connect (lazy pool)."""
    monkeypatch.setenv("DATA_AGENT_ANTHROPIC_API_KEY", "sk-test")
    agent = DataAnalyst(db_url=seeded_db_url)
    # No connection attempt yet — connect happens on first ask() (W2) or explicit open.
    assert agent._backend is not None
    assert agent._backend._pool is None  # not connected yet


@pytest.mark.asyncio
async def test_close_is_idempotent(
    monkeypatch: pytest.MonkeyPatch, seeded_db_url: str
) -> None:
    monkeypatch.setenv("DATA_AGENT_ANTHROPIC_API_KEY", "sk-test")
    agent = DataAnalyst(db_url=seeded_db_url)
    await agent.close()  # close without connect: no-op
    await agent.close()  # second close: still no-op


def test_ask_sync_outside_loop_calls_ask(
    monkeypatch: pytest.MonkeyPatch, seeded_db_url: str
) -> None:
    """ask_sync running-loop guard: outside a loop, works (calls asyncio.run).
    Inside a loop, raises RuntimeError pointing to ask()."""
    monkeypatch.setenv("DATA_AGENT_ANTHROPIC_API_KEY", "sk-test")
    agent = DataAnalyst(db_url=seeded_db_url)

    # We can't test the success path without W2's ask() implementation.
    # Verify the loop-detection branch raises the right error when in a loop.
    async def _inside_loop() -> None:
        with pytest.raises(RuntimeError, match="ask_sync.*running event loop"):
            agent.ask_sync("ignored")

    asyncio.run(_inside_loop())
