"""Shared pytest fixtures.

pytest-postgresql provides a `postgresql` fixture (a running PG instance per test).
We seed a tiny schema so list_tables/get_table_schema tests have content.
"""

import psycopg
import pytest
from pytest_postgresql import factories

# PG binary is provided by pytest-postgresql plugin (uses pg_ctl from PATH).
postgresql_proc = factories.postgresql_proc(port=None)
postgresql = factories.postgresql("postgresql_proc")


@pytest.fixture
def db_url(postgresql: psycopg.Connection) -> str:
    """Return a DSN that points at the per-test PG instance."""
    info = postgresql.info
    return f"postgresql://{info.user}@{info.host}:{info.port}/{info.dbname}"


@pytest.fixture
def seeded_db_url(db_url: str) -> str:
    """Create a `users` table with sample rows for integration tests."""
    with psycopg.connect(db_url) as conn, conn.cursor() as cur:
        cur.execute(
            """
            CREATE TABLE users (
                id INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                email TEXT,
                created_at TIMESTAMP DEFAULT NOW()
            )
            """
        )
        cur.execute(
            "INSERT INTO users (id, name, email) VALUES (1, 'alice', 'a@x.com'), (2, 'bob', NULL)"
        )
        conn.commit()
    return db_url
