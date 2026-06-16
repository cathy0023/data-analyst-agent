"""DataAnalyst: embeddable NL2SQL agent.

W1 lands __init__ + close + ask_sync running-loop guard. W2 lands ask() and
the tool-use loop. The class is constructed eagerly (fail-fast on config
errors) but the connection pool is lazy (opened on first ask() call).
"""

from __future__ import annotations

import asyncio

from data_analyst_agent.config import ConfigError, Settings
from data_analyst_agent.executor.postgres import PostgresBackend
from data_analyst_agent.models import Answer


class DataAnalyst:
    """Embeddable NL2SQL agent.

    Thread-safety contract (RFC DATA-001 §Public API Contract, v3):
      * Single DataAnalyst instance is safe to share across asyncio tasks
        running in the SAME event loop. Internal state is immutable after __init__.
      * Cross-thread sharing is NOT supported — the psycopg AsyncConnectionPool
        is bound to the event loop that created it. Each OS thread that needs
        to call ask() must construct its own DataAnalyst (cheap; pool is lazy).
      * Fork-safety: NOT fork-safe. Forked children must call close() in the
        parent and re-construct in the child.
      * Multiprocessing: each worker process constructs its own instance.

    Lifecycle:
      * Construct once per process (or once per thread).
      * Use `async with DataAnalyst(...) as agent:` for auto-cleanup, or call
        `await agent.close()` explicitly. close() is idempotent.

    Behavior with in-flight ask() at close():
      * Per psycopg AsyncConnectionPool semantics, close() waits for
        checked-out connections to be returned. In-flight queries are NOT
        cancelled — they run to completion (or until statement_timeout fires).
      * Callers should await or cancel background tasks before close().
    """

    def __init__(self, *, db_url: str, settings: Settings | None = None) -> None:
        # Fail-fast on missing API key. Settings() raises if env is unset.
        try:
            self._settings = settings or Settings(db_url=db_url)
        except Exception as exc:
            if "anthropic_api_key" in str(exc).lower() or "ANTHROPIC_API_KEY" in str(exc):
                raise ConfigError(
                    "缺少 ANTHROPIC_API_KEY 环境变量，请在 shell 或 .env 中设置 "
                    "(Missing ANTHROPIC_API_KEY env var; set it in shell or .env)."
                ) from exc
            raise

        # If settings was passed in but db_url differs, prefer the explicit arg.
        if db_url and self._settings.db_url != db_url:
            self._settings = self._settings.model_copy(update={"db_url": db_url})

        # Lazy pool — connect on first ask() or explicit open.
        self._backend = PostgresBackend(settings=self._settings)
        self._closed = False

    async def ask(self, question: str, *, conversation_id: str | None = None) -> Answer:
        """Run the NL → SQL → query → conclusion agent loop.

        W2 implements this. W1 raises NotImplementedError to make the gap explicit.
        """
        raise NotImplementedError("DataAnalyst.ask() is implemented in W2 (Task: Tool layer + Agent loop).")

    def ask_sync(self, question: str) -> Answer:
        """Sync alias for non-async callers (scripts / REPL / notebooks)."""
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(self.ask(question))
        raise RuntimeError(
            "ask_sync() cannot run inside a running event loop "
            "(e.g. inside FastAPI handler, Jupyter cell with asyncio, "
            "or nested asyncio.run). Use 'await agent.ask(question)' instead."
        )

    async def close(self) -> None:
        """Release the connection pool. Idempotent."""
        if self._closed:
            return
        self._closed = True
        if self._backend is not None:
            await self._backend.close()

    async def __aenter__(self) -> DataAnalyst:
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        await self.close()
