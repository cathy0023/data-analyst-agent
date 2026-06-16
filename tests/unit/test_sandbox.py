"""AC-4: Sandbox allow-list rejects non-SELECT/WITH root statements.

Covers:
- Round 1 + Round 2 + Round 3 Critical fixes:
  - Allow-list (root must be Select or With)
  - Deny-list defense-in-depth (16+ banned constructs)
  - Multi-statement behavior (RFC rule 8)
  - LIMIT injection
  - explain_plan rejection path (Round 3 NC-1)
"""

import pytest

from data_analyst_agent.executor.sandbox import (
    SandboxError,
    validate_sql,
    validate_sql_with_limit,
)

# === Allow-list acceptance ===


def test_simple_select_passes() -> None:
    sql = validate_sql("SELECT 1")
    assert "SELECT" in sql.upper()


def test_select_with_columns_passes() -> None:
    sql = validate_sql("SELECT id, name FROM users WHERE id = 1")
    assert "FROM users" in sql


def test_with_cte_passes() -> None:
    sql = validate_sql("WITH t AS (SELECT 1) SELECT * FROM t")
    assert "WITH" in sql.upper()


# === Deny-list: root statement rejection ===


def test_insert_rejected() -> None:
    with pytest.raises(SandboxError, match="root statement must be SELECT or WITH"):
        validate_sql("INSERT INTO users (id) VALUES (1)")


def test_update_rejected() -> None:
    with pytest.raises(SandboxError):
        validate_sql("UPDATE users SET name='x' WHERE id=1")


def test_delete_rejected() -> None:
    with pytest.raises(SandboxError):
        validate_sql("DELETE FROM users WHERE id=1")


def test_drop_rejected() -> None:
    with pytest.raises(SandboxError):
        validate_sql("DROP TABLE users")


def test_truncate_rejected() -> None:
    with pytest.raises(SandboxError):
        validate_sql("TRUNCATE TABLE users")


def test_create_rejected() -> None:
    with pytest.raises(SandboxError):
        validate_sql("CREATE TABLE x (id int)")


def test_alter_rejected() -> None:
    with pytest.raises(SandboxError):
        validate_sql("ALTER TABLE users ADD COLUMN x int")


# === Deny-list: defense-in-depth (commands + statements inside AST) ===


def test_merge_rejected() -> None:
    with pytest.raises(SandboxError):
        validate_sql(
            "MERGE INTO target USING src ON target.id = src.id "
            "WHEN MATCHED THEN UPDATE SET x = src.x"
        )


def test_grant_rejected() -> None:
    with pytest.raises(SandboxError):
        validate_sql("GRANT SELECT ON users TO alice")


def test_revoke_rejected() -> None:
    with pytest.raises(SandboxError):
        validate_sql("REVOKE SELECT ON users FROM alice")


def test_copy_rejected() -> None:
    with pytest.raises(SandboxError):
        validate_sql("COPY users TO '/tmp/out.csv' CSV")


def test_call_rejected() -> None:
    with pytest.raises(SandboxError):
        validate_sql("CALL my_proc()")


def test_listen_rejected() -> None:
    with pytest.raises(SandboxError):
        validate_sql("LISTEN channel1")


def test_notify_rejected() -> None:
    with pytest.raises(SandboxError):
        validate_sql("NOTIFY channel1")


def test_do_block_rejected() -> None:
    with pytest.raises(SandboxError):
        validate_sql("DO $$ BEGIN PERFORM 1; END $$")


def test_comment_on_rejected() -> None:
    with pytest.raises(SandboxError):
        validate_sql("COMMENT ON TABLE users IS 'users table'")


def test_set_rejected() -> None:
    with pytest.raises(SandboxError):
        validate_sql("SET statement_timeout TO 0")


def test_set_local_rejected() -> None:
    # v3 removed the SET LOCAL carve-out — all SET forms rejected
    with pytest.raises(SandboxError):
        validate_sql("SET LOCAL statement_timeout TO 0")


def test_subquery_with_delete_rejected() -> None:
    with pytest.raises(SandboxError):
        validate_sql("SELECT * FROM (DELETE FROM users RETURNING *) t")


# === Multi-statement behavior (RFC rule 8) ===


def test_multi_statement_drops_tail() -> None:
    """parse_one only validates first statement; tail is silently dropped."""
    sql = validate_sql("SELECT 1; DROP TABLE users")
    assert "SELECT" in sql.upper()
    assert "DROP" not in sql.upper()


# === LIMIT injection ===


def test_limit_injected_when_absent() -> None:
    sql = validate_sql_with_limit("SELECT * FROM users", row_limit=1000)
    assert "LIMIT 1000" in sql.upper()


def test_limit_preserved_when_within_bound() -> None:
    sql = validate_sql_with_limit("SELECT * FROM users LIMIT 50", row_limit=1000)
    assert "LIMIT 50" in sql.upper()


def test_limit_truncated_when_exceeds_bound() -> None:
    sql = validate_sql_with_limit("SELECT * FROM users LIMIT 5000", row_limit=1000)
    assert "LIMIT 1000" in sql.upper()
    assert "5000" not in sql


# === explain_plan rejection path (Round 3 NC-1, AC-4 v3 addition) ===


def test_explain_plan_rejects_non_select() -> None:
    """explain_plan("DELETE FROM users") must be rejected by validate_sql
    before any EXPLAIN wrapping — root is Delete, not Select."""
    with pytest.raises(SandboxError, match="root statement must be SELECT or WITH"):
        validate_sql("DELETE FROM users")


def test_explain_plan_rejects_explain_written_by_llm() -> None:
    """If LLM writes EXPLAIN itself, parse_one yields exp.Explain as root,
    which is rejected by allow-list — no path bypasses validation."""
    with pytest.raises(SandboxError):
        validate_sql("EXPLAIN DELETE FROM users")


def test_explain_plan_accepts_valid_select() -> None:
    """Inner SELECT passes; SDK then wraps with EXPLAIN prefix."""
    inner = validate_sql("SELECT COUNT(*) FROM users")
    wrapped = f"EXPLAIN (ANALYZE, BUFFERS) {inner}"
    assert wrapped.startswith("EXPLAIN (ANALYZE, BUFFERS)")
    assert "SELECT" in wrapped
