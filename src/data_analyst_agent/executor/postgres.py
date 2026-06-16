"""PostgresBackend: concrete class owning the connection pool and execution.

Per RFC DATA-001 §Design/Architecture + §Implementation/Module Layout.
NO ABC (YAGNI per Decision #1). W1 lands connect / close / list_tables /
get_table_schema. W2 adds execute / explain.
"""

from urllib.parse import quote

from psycopg_pool import AsyncConnectionPool

from data_analyst_agent.config import Settings


class PostgresBackend:
    """Concrete Postgres backend. One instance owns one AsyncConnectionPool."""

    def __init__(self, *, settings: Settings) -> None:
        self._settings = settings
        self._pool: AsyncConnectionPool | None = None

    @property
    def _dsn_with_options(self) -> str:
        """Append statement_timeout at DSN level (RFC rule 4: not via SET LOCAL).

        The whole options string must be URL-encoded because libpq's URI parser
        is strict about reserved characters: spaces, ``=``, ``&`` all need
        percent-encoding inside the ``options`` query parameter value.
        """
        timeout_ms = int(self._settings.statement_timeout_seconds * 1000)
        # PG options format: "-c statement_timeout=2000 -c application_name=foo"
        # URL-encode the whole string so libpq's URI parser accepts it.
        raw_options = f"-c statement_timeout={timeout_ms} -c application_name=data-analyst-agent"
        encoded = quote(raw_options, safe="")
        sep = "&" if "?" in self._settings.db_url else "?"
        return f"{self._settings.db_url}{sep}options={encoded}"

    async def connect(self) -> None:
        """Open the pool. Idempotent: subsequent calls are no-op."""
        if self._pool is not None:
            return
        self._pool = AsyncConnectionPool(
            conninfo=self._dsn_with_options,
            min_size=self._settings.min_pool_size,
            max_size=self._settings.max_pool_size,
            open=False,
        )
        await self._pool.open()

    async def close(self) -> None:
        """Close the pool. Idempotent."""
        if self._pool is None:
            return
        await self._pool.close()
        self._pool = None

    def _require_pool(self) -> AsyncConnectionPool:
        if self._pool is None:
            raise RuntimeError(
                "PostgresBackend not connected; call await backend.connect() first."
            )
        return self._pool

    async def list_tables(self) -> list[str]:
        """Return list of table names in the public schema."""
        pool = self._require_pool()
        async with pool.connection() as conn, conn.cursor() as cur:
            await cur.execute(
                """
                SELECT table_name
                FROM information_schema.tables
                WHERE table_schema = 'public'
                  AND table_type = 'BASE TABLE'
                ORDER BY table_name
                """
            )
            rows = await cur.fetchall()
        return [str(r[0]) for r in rows]

    async def get_table_schema(
        self, table_name: str
    ) -> list[tuple[str, str, str, str | None]]:
        """Return [(column_name, data_type, is_nullable, comment), ...] for a table.

        Comment comes from col_description; may be None if no comment set.
        """
        pool = self._require_pool()
        async with pool.connection() as conn, conn.cursor() as cur:
            await cur.execute(
                """
                SELECT
                    c.column_name,
                    c.data_type,
                    c.is_nullable,
                    col_description(
                      (c.table_schema||'.'||c.table_name)::regclass,
                      c.ordinal_position
                    )
                FROM information_schema.columns c
                WHERE c.table_schema = 'public' AND c.table_name = %s
                ORDER BY c.ordinal_position
                """,
                (table_name,),
            )
            rows = await cur.fetchall()
        return [
            (str(r[0]), str(r[1]), str(r[2]), r[3] if r[3] is None else str(r[3]))
            for r in rows
        ]

    # execute() and explain() added in W2 (Task: Tool layer + Agent loop).
