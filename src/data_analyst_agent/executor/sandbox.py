"""SQL sandbox: allow-list (primary) + deny-list (defense-in-depth) + LIMIT injection.

Per RFC DATA-001 §Security & Sandboxing. The LLM never writes safety-critical
syntactic wrappers (LIMIT, statement_timeout, EXPLAIN prefix) — SDK code does.
"""

import sqlglot
from sqlglot import exp


class SandboxError(Exception):
    """Raised when SQL fails sandbox validation."""


# Statement types allowed at AST root.
_ALLOWED_ROOT_TYPES = (exp.Select, exp.With)

# Deny-list (defense-in-depth; checked anywhere in AST, including subqueries).
# Per RFC rule 2: SET covers all forms (no SET LOCAL carve-out in v3+).
_DENY_NODE_TYPES: tuple[type[exp.Expression], ...] = (
    exp.Insert,
    exp.Update,
    exp.Delete,
    exp.Drop,
    exp.Alter,
    exp.AlterColumn,
    exp.TruncateTable,
    exp.Create,
    exp.Merge,
    exp.Command,  # covers GRANT, REVOKE, COPY, CALL, LISTEN, NOTIFY, COMMENT ON, SET, etc.
)


def _check_root(parsed: exp.Expression) -> None:
    if not isinstance(parsed, _ALLOWED_ROOT_TYPES):
        kind = type(parsed).__name__
        raise SandboxError(
            f"Sandbox rejection: root statement must be SELECT or WITH; got {kind}."
        )


def _walk_and_deny(parsed: exp.Expression) -> None:
    for node in parsed.walk():
        # walk() yields tuples; sqlglot >= 25 yields (node, parent, key)
        n = node[0] if isinstance(node, tuple) else node
        if isinstance(n, _DENY_NODE_TYPES):
            kind = type(n).__name__
            raise SandboxError(
                f"Sandbox rejection: AST contains forbidden node {kind}."
            )


def _inject_limit(parsed: exp.Expression, row_limit: int) -> exp.Expression:
    """Append LIMIT row_limit if absent; truncate if exceeds."""
    for select in parsed.find_all(exp.Select):
        existing = select.args.get("limit")
        if existing is None:
            select.set("limit", exp.Limit(expression=exp.Literal.number(row_limit)))
        else:
            try:
                limit_expr = existing.expression  # type: ignore[union-attr]
                current = int(limit_expr.name)  # type: ignore[union-attr]
            except (AttributeError, ValueError):
                continue
            if current > row_limit:
                select.set(
                    "limit",
                    exp.Limit(expression=exp.Literal.number(row_limit)),
                )
    return parsed


def validate_sql(sql: str) -> str:
    """Validate SQL via allow-list + deny-list. Does NOT inject LIMIT.

    Use this for ``explain_plan`` (which adds its own EXPLAIN prefix but does
    not need LIMIT — EXPLAIN ANALYZE already executes the underlying query,
    and LIMIT would distort the plan).
    """
    try:
        parsed = sqlglot.parse_one(sql, dialect="postgres")
    except Exception as exc:
        raise SandboxError(f"Sandbox rejection: SQL failed to parse: {exc}") from exc

    if parsed is None:
        raise SandboxError("Sandbox rejection: SQL parsed to None.")

    _check_root(parsed)
    _walk_and_deny(parsed)
    return parsed.sql(dialect="postgres")


def validate_sql_with_limit(sql: str, *, row_limit: int) -> str:
    """Validate SQL AND inject/truncate LIMIT. Use this for ``execute_sql``."""
    try:
        parsed = sqlglot.parse_one(sql, dialect="postgres")
    except Exception as exc:
        raise SandboxError(f"Sandbox rejection: SQL failed to parse: {exc}") from exc

    if parsed is None:
        raise SandboxError("Sandbox rejection: SQL parsed to None.")

    _check_root(parsed)
    _walk_and_deny(parsed)
    _inject_limit(parsed, row_limit)
    return parsed.sql(dialect="postgres")
