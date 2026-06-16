"""AC-18: pyproject.toml dependencies match RFC DATA-001 §Implementation/Dependencies."""

import re
from pathlib import Path

import tomllib

PYPROJECT = Path(__file__).parent.parent / "pyproject.toml"

EXPECTED_RUNTIME = {
    "anthropic",
    "sqlalchemy",
    "psycopg",
    "sqlglot",
    "pydantic",
    "pydantic-settings",
    "python-dotenv",
    "python-json-logger",
}

EXPECTED_DEV = {
    "pytest",
    "pytest-cov",
    "pytest-asyncio",
    "mypy",
    "ruff",
    "respx",
    "freezegun",
    "pytest-postgresql",
}

# Split on whitespace, [, ;, and version constraint operators (>=, <, >, <=, ==, !=, ~=)
_DEP_NAME_RE = re.compile(r"[\s\[;><=!~]+")


def _load_pyproject() -> dict:
    with PYPROJECT.open("rb") as f:
        return tomllib.load(f)


def _extract_dep_names(deps: list[str]) -> set[str]:
    names: set[str] = set()
    for d in deps:
        # Strip env markers, extras, and version constraints from the spec
        name = _DEP_NAME_RE.split(d, maxsplit=1)[0]
        if name:
            names.add(name)
    return names


def test_runtime_dependencies_match_rfc() -> None:
    data = _load_pyproject()
    actual = _extract_dep_names(data["project"]["dependencies"])
    assert actual == EXPECTED_RUNTIME, (
        f"Missing: {EXPECTED_RUNTIME - actual}, Extra: {actual - EXPECTED_RUNTIME}"
    )


def test_dev_dependencies_match_rfc() -> None:
    data = _load_pyproject()
    actual = _extract_dep_names(data["project"]["optional-dependencies"]["dev"])
    assert actual == EXPECTED_DEV, (
        f"Missing: {EXPECTED_DEV - actual}, Extra: {actual - EXPECTED_DEV}"
    )

