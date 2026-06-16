"""AC-5/AC-6: PostgresBackend — connect/close/list_tables/get_table_schema + DSN statement_timeout."""

import time

import psycopg
import pytest

from data_analyst_agent.config import Settings
from data_analyst_agent.executor.postgres import PostgresBackend


@pytest.mark.asyncio
async def test_connect_and_close(
    seeded_db_url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DATA_AGENT_ANTHROPIC_API_KEY", "sk-test")
    settings = Settings(db_url=seeded_db_url)
    backend = PostgresBackend(settings=settings)
    await backend.connect()
    await backend.close()  # idempotent
    await backend.close()  # second close is no-op


@pytest.mark.asyncio
async def test_list_tables(
    seeded_db_url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DATA_AGENT_ANTHROPIC_API_KEY", "sk-test")
    settings = Settings(db_url=seeded_db_url)
    backend = PostgresBackend(settings=settings)
    await backend.connect()
    try:
        tables = await backend.list_tables()
        assert "users" in tables
    finally:
        await backend.close()


@pytest.mark.asyncio
async def test_get_table_schema(
    seeded_db_url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DATA_AGENT_ANTHROPIC_API_KEY", "sk-test")
    settings = Settings(db_url=seeded_db_url)
    backend = PostgresBackend(settings=settings)
    await backend.connect()
    try:
        schema = await backend.get_table_schema("users")
        col_names = [c[0] for c in schema]
        assert "id" in col_names
        assert "name" in col_names
        assert "email" in col_names
    finally:
        await backend.close()


@pytest.mark.asyncio
async def test_statement_timeout_kills_pg_sleep(
    seeded_db_url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """AC-5: pg_sleep(60) killed at ~2s via DSN-level statement_timeout.

    Verifies the LLM cannot bypass the timeout with RESET statement_timeout.
    """
    monkeypatch.setenv("DATA_AGENT_ANTHROPIC_API_KEY", "sk-test")
    settings = Settings(
        db_url=seeded_db_url, statement_timeout_seconds=2.0
    )  # shorter for test speed
    backend = PostgresBackend(settings=settings)
    await backend.connect()
    try:
        pool = backend._require_pool()
        start = time.monotonic()
        with pytest.raises(psycopg.errors.QueryCanceled):
            async with pool.connection() as conn, conn.cursor() as cur:
                # Even an explicit RESET attempt cannot override DSN-level setting.
                await cur.execute("RESET statement_timeout")
                await cur.execute("SELECT pg_sleep(60)")
        elapsed = time.monotonic() - start
        # Timeout fires at ~2s, not 60s. Allow generous slack for CI.
        assert elapsed < 10.0, f"statement_timeout did not fire: elapsed={elapsed:.1f}s"
    finally:
        await backend.close()
