# CLAUDE.md — data-analyst-agent

## Project Overview

`data-analyst-agent` is a Python SDK for embedding conversational data analysis (NL → SQL → result → conclusion) into host applications. Currently in prototype / RFC stage.

- **Language**: Python 3.10+
- **Architecture**: Three-layer (Agent / Tool / Executor)
- **Database**: PostgreSQL (prototype default), MySQL TBD
- **LLM**: Claude (default) / OpenAI, native tool use

## rfc-driven-dev config

- `package_manager`: pip
- `review_score_threshold`: 8
- `max_review_rounds`: 3
- `max_fix_rounds`: 2
- `target_branch`: main
- `series_prefix`: DATA

## Dev Commands

```bash
# Install in editable mode with dev deps
pip install -e ".[dev]"

# Run tests
pytest

# Type check
mypy src/

# Lint
ruff check src/ tests/
```

## Repository Layout

```
data-analyst-agent/
├── CLAUDE.md                  # This file
├── README.md
├── pyproject.toml
├── .gitignore
├── docs/
│   └── rfcs/                  # RFC workflow (inbox → draft → approved → completed)
├── src/
│   └── data_analyst_agent/    # Package source
└── tests/                     # Test suite
```

## RFC Workflow

This project follows RFC-driven development. See [docs/rfcs/README.md](docs/rfcs/README.md) for details.

- `/rfc-brainstorm` → Capture raw requirements in `docs/rfcs/inbox/`
- `/rfc-init` → Initialize RFC directory structure (already done)
- `/rfc-driven-dev docs/rfcs/inbox/<file>.md` → Full pipeline (research → RFC → plan → implement → review → deliver)
