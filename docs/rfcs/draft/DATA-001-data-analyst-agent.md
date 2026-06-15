---
rfc_id: DATA-001
title: "DATA-001: Conversational Data Analysis Agent SDK (Prototype)"
created: 2026-06-15
status: Draft
series: DATA
author: data-analyst-agent contributors
reviewers: []
related_inbox: inbox/2026-06-15-data-analyst-agent.md
---

# DATA-001: Conversational Data Analysis Agent SDK (Prototype)

## Goals

1. **Ship a `pip install`-able Python SDK** (`data-analyst-agent`) that lets developers embed conversational data analysis into their applications with ≤10 lines of integration code.
2. **Validate the three-layer architecture** (Agent / Tool / Executor) end-to-end against a demo PostgreSQL database with 20–30 representative questions.
3. **Hit ≥80% execution-accuracy (EX)** on the in-repo demo question set, with NL → SQL → query → conclusion as a single agent loop.
4. **Identify quantified technical limits** of the chosen stack (Anthropic Claude tool use + native loop + sqlglot sandbox + pgvector-ready schema injection) — output a metrics report covering accuracy, P95 latency, token cost, and failure modes.
5. **Lay the architectural foundation** for production hardening (Backend abstraction, sandboxing, multi-model routing, observability) without building production-readiness features themselves.

## Background

### Origin

Originated from `/rfc-brainstorm` on 2026-06-15 (see `inbox/2026-06-15-data-analyst-agent.md`). The user classified this as a **technical prototype validation** project — motivation is to de-risk the "LLM + tool use + NL2SQL in an embeddable SDK form factor" path before any production commitment.

### Current State

The repository is freshly initialized (commit `41068a1`): `pyproject.toml` with `dependencies = []`, an empty `src/data_analyst_agent/__init__.py`, an empty `tests/__init__.py`, tooling configured (pytest ≥8, mypy strict, ruff), and the RFC workflow directory structure. No business code, no CI, no demo data.

### Why Now

- **Industry signal**: Spider 2.0 (real-world enterprise schemas, >1000 columns) dropped GPT-4o from Spider 1.0's 86.6% to **10.1%** — proving that full-schema injection is no longer viable and Agent-loop + schema-linking is the new SOTA. The window to validate a modern stack is now.
- **Embedded-SDK gap**: The top open-source NL2SQL libs (Vanna v2.0 archived 2026-03-29; DB-GPT and WrenAI server-first) do not cleanly serve the "embed me as a library" use case.
- **Tooling maturity**: Anthropic tool use protocol, `sqlglot` SQL transpilation, and `pgvector` are all production-ready in 2026 — the prototype can stand on stable primitives without framework lock-in.

### Pain Points Addressed

- Developers currently hand-roll NL2SQL with brittle prompt chains; the SDK must encapsulate best practices (sandboxing, schema retrieval, multi-model routing) so consumers don't repeat them.
- Internal/business teams need a reusable library to drop into multiple products, avoiding duplicate prototyping.

## Design

### Architecture: Three-Layer (selected as "方案 C" in brainstorm)

The SDK is structured around explicit layers, each independently testable, with strict directional dependencies (Agent → Tool → Executor; never reverse).

```
┌──────────────────────────────────────────────────────────────┐
│  Public API:  DataAnalyst(db_url=...).ask(question) -> Answer  │
└──────────────────────────────────────────────────────────────┘
                              │
┌─────────────────────────────▼────────────────────────────────┐
│  Agent Layer  (agent.py)                                       │
│  - tool use loop: while stop_reason == "tool_use"              │
│  - multi-model routing (Sonnet 4.6 default, Haiku 4.5 simple)  │
│  - safety guards: max_iter=8, repeat-failure circuit breaker   │
└─────────────────────────────┬────────────────────────────────┘
                              │ invokes
┌─────────────────────────────▼────────────────────────────────┐
│  Tool Layer  (tools/{list_tables,get_schema,execute_sql,explain_plan}.py)  │
│  - each tool: Pydantic input/output schema                     │
│  - tool returns "columns + types + comments + sample values"   │
│    (not raw DDL) for schema-related tools                      │
└─────────────────────────────┬────────────────────────────────┘
                              │ delegates SQL to
┌─────────────────────────────▼────────────────────────────────┐
│  Executor Layer  (executor/)                                   │
│  - Backend ABC + PostgreSQL implementation                     │
│  - sqlglot-based sandbox: dialect normalize + danger deny      │
│  - read-only DB user + statement_timeout + row_limit           │
│  - SQL-hash cache (TTL)                                        │
└────────────────────────────────────────────────────────────────┘
```

### Schema Injection Strategy (tiered by scale)

| DB size | Strategy | Token Cost |
|---------|----------|------------|
| ≤30 tables | Full schema in system prompt | ~1–4k tokens |
| 30–200 tables | `get_schema(tables: list[str])` on-demand tool, cached | ~300–500 tokens per call |
| >200 tables | pgvector embedding of table/column summaries + schema linking | ~2–4k tokens per query (post-retrieval) |

For the prototype we implement **tier 1 + tier 2** (full + on-demand tool). Tier 3 (pgvector) is **explicitly deferred** but the `Backend` ABC must not preclude it.

### Business Glossary (cross-cutting)

A YAML file (`glossary.yaml` or per-DB) maps business terms → table/column, synonyms, units, sample values. The Agent reads this in the system prompt. Format inspired by Snowflake Cortex Analyst's semantic model spec and WrenAI's MDL.

### LLM Protocol

- **Primary**: Anthropic Claude Sonnet 4.6 (`claude-sonnet-4-6`) via native tool use.
- **Router**: Claude Haiku 4.5 (`claude-haiku-4-5-20251001`) for single-table / simple aggregation questions (cost ~1/30 of Sonnet). Routing heuristic: question length + presence of multi-table keywords.
- **Fallback option (not implemented in prototype)**: OpenAI tool use behind the same `LLMClient` ABC; documented but not wired.

### Security & Sandboxing

- **SQL safety**: All generated SQL passes through `sqlglot.parse_one(sql, dialect=...)` → deny `INSERT/UPDATE/DELETE/DROP/ALTER/TRUNCATE` → enforce `LIMIT` injection if absent → enforce `statement_timeout` via `SET LOCAL`.
- **DB user**: SDK connects with a DB user that has `SELECT`-only grants (documented; enforced via config check at init).
- **Result redaction**: configurable regex-based redaction (phone, email, ID-card patterns) — opt-in.

### Observability

- Structured logs (stdlib `logging` + JSON formatter) per tool call: tool name, input hash, output row count, duration, tokens consumed.
- Optional OpenTelemetry tracing hooks (deferred — interface only).

### Non-Goals (preserved from brainstorm)

- No productization (auth, multi-tenant, billing, SSO).
- No advanced statistical modeling (forecasting, clustering, ML training).
- No multi-source abstraction in the prototype (Backend ABC exists; only PostgreSQL implemented). MySQL is documented but not implemented.
- No front-end chart rendering in the SDK (returns structured data only; rendering is the host app's job).
- No pgvector schema retrieval (tier 3) in the prototype.

## Implementation

### Module Layout

```
src/data_analyst_agent/
├── __init__.py              # Public API: DataAnalyst, Answer, AskError
├── agent.py                 # Agent layer (tool use loop, model router)
├── config.py                # Pydantic Settings (db_url, model, timeouts)
├── models.py                # Data models: Answer, ToolCall, TokenUsage
├── logging_setup.py         # Structured logging config
├── llm/                     # LLM client ABC + Anthropic impl
│   ├── __init__.py
│   ├── base.py              # LLMClient ABC
│   └── anthropic_client.py
├── tools/                   # Tool layer
│   ├── __init__.py
│   ├── base.py              # Tool protocol + registry
│   ├── list_tables.py
│   ├── get_schema.py
│   ├── execute_sql.py
│   └── explain_plan.py
└── executor/                # Executor layer
    ├── __init__.py
    ├── base.py              # Backend ABC
    ├── postgres.py          # PostgreSQL implementation
    └── sandbox.py           # sqlglot-based SQL guard
```

### Dependencies (prototype runtime)

```toml
dependencies = [
    "anthropic>=0.40,<1.0",
    "sqlalchemy>=2.0",
    "psycopg[binary,pool]>=3.2",
    "sqlglot>=25.0",
    "pydantic>=2.7",
    "pydantic-settings>=2.3",
    "python-dotenv>=1.0",
]
```

Dev dependencies (extend existing):

```toml
[project.optional-dependencies]
dev = [
    "pytest>=8.0",
    "pytest-cov>=4.0",
    "pytest-asyncio>=0.23",
    "mypy>=1.10",
    "ruff>=0.5",
    "respx>=0.21",            # HTTP mock for Anthropic API
    "freezegun>=1.5",
]
```

### Test Strategy

| Layer | Test Type | Mock Strategy |
|-------|-----------|---------------|
| Executor / sandbox | Unit (no DB) | sqlglot parsing tests; danger-SQL rejection tests |
| Executor / postgres | Integration (real PG) | `pytest-postgresql` or docker-compose PG; seed from `tests/fixtures/demo_db.sql` |
| Tools | Unit | Mock `Backend` ABC; assert tool contract |
| Agent loop | Integration | Mock `LLMClient` returning canned tool_use sequences |
| End-to-end | Integration | Real PG + mocked LLM (deterministic); 30 demo questions |

### Demo Dataset & Question Set

- **Dataset**: `tests/fixtures/demo_db.sql` — synthetic e-commerce schema (~10 tables: `users`, `orders`, `order_items`, `products`, `categories`, `regions`, `events`, `coupons`, `refunds`, `inventory`). Seed ~10k rows.
- **Question set**: `tests/fixtures/questions.yaml` — 30 questions tagged by difficulty (easy/medium/hard), each with: natural-language question, expected SQL or expected row-shape, tags.
- **Eval script**: `scripts/eval.py` — runs all questions, outputs `accuracy_report.json` with per-question pass/fail + token usage + latency.

### Milestones (4-week time-box)

| Week | Deliverable | Gate |
|------|-------------|------|
| W1 | Backend ABC + PostgreSQL impl + sandbox + 4 tools (no LLM) | All tool unit tests pass; sandbox rejects all DML |
| W2 | Anthropic LLMClient + Agent loop + Agent integration tests | Canned-tool-use tests pass; mock end-to-end green |
| W3 | Demo dataset + 30 questions + eval script + accuracy tuning | ≥80% EX on demo set; metrics report drafted |
| W4 | SDK packaging + `examples/demo.py` + README + metrics report | `pip install -e .` works; 3rd-party clone → run in ≤5 min |

## Acceptance Criteria

Each criterion is independently verifiable.

| # | Criterion | Verification |
|---|-----------|--------------|
| AC-1 | `pip install -e ".[dev]"` succeeds on Python 3.10+ | Run install in fresh venv; exit 0 |
| AC-2 | `from data_analyst_agent import DataAnalyst` resolves | `python -c "from data_analyst_agent import DataAnalyst"` exits 0 |
| AC-3 | A 3-line integration (`DataAnalyst(db_url=...).ask("...")`) returns a structured `Answer` object against the demo DB | `examples/demo.py` runs end-to-end |
| AC-4 | Sandbox rejects all of: `INSERT`, `UPDATE`, `DELETE`, `DROP`, `ALTER`, `TRUNCATE`, `GRANT`, `REVOKE` | `tests/unit/test_sandbox.py` ≥8 test cases all pass |
| AC-5 | Sandbox enforces `LIMIT` and `statement_timeout` on every executed SQL | Unit tests verify via `sqlglot.parse_one` post-processing |
| AC-6 | `Backend` ABC exists; `PostgresBackend` implements it; SDK initializes correctly given a PG connection string | `tests/integration/test_postgres_backend.py` green |
| AC-7 | Tool layer has `list_tables`, `get_schema`, `execute_sql`, `explain_plan`; each has Pydantic input/output schema | `tests/unit/test_tools.py` covers each tool's contract |
| AC-8 | Agent loop terminates within `max_iter=8` even on adversarial input | Property-based test with mock LLM returning tool_use forever |
| AC-9 | `scripts/eval.py` produces `accuracy_report.json` with per-question pass/fail + token usage | Run produces non-empty JSON with 30 entries |
| AC-10 | Demo question set accuracy ≥80% (EX, execution-result-equality modulo ordering) | `accuracy_report.json` `"overall_accuracy" >= 0.80` |
| AC-11 | P95 end-to-end latency ≤15s on demo set (single-threaded, Sonnet 4.6) | `accuracy_report.json` aggregates p95 latency |
| AC-12 | `examples/demo.py` runs end-to-end with `ANTHROPIC_API_KEY` env var, no other setup | Manual run from clean clone |
| AC-13 | Metrics report (`docs/metrics-report.md`) covers: accuracy, P50/P95 latency, token cost per question, top-3 failure modes | File exists; contains the 4 sections |
| AC-14 | Multi-model routing: questions tagged "easy" route to Haiku 4.5; "hard" to Sonnet 4.6 | Unit test on router; logs confirm routing in eval |
| AC-15 | `mypy --strict src/` and `ruff check src/ tests/` both clean | CI command exits 0 |

## Notes

### Key Decisions (with evidence)

1. **Native Anthropic tool use over pydantic-ai/LangChain** — Industry research (Stage 1 Agent 2) showed the `while stop_reason=="tool_use"` loop is ~100 LOC and gives best debuggability; framework overhead does not pay off for the prototype's "see every step" goal.
2. **PostgreSQL-only in prototype, Backend ABC reserved** — Resolution of inbox "待解决问题 #1": the contradiction between "no multi-source abstraction" (Non-Goal) and "PG or MySQL" (constraint) is resolved by implementing PG only and documenting MySQL as a follow-up; the ABC exists but has one implementation.
3. **EX (execution accuracy) over SQL string equality** — Industry research showed Spider/BIRD have shifted to EX because equivalent SQL can have different surface forms. The eval script normalizes via `sqlglot` and compares result-row-sets modulo ordering.
4. **Tiered schema injection** — Resolution of inbox "待解决问题 #4": tier 1 (full) + tier 2 (on-demand tool) implemented; tier 3 (pgvector) deferred. Token budget 8–15k for 100 tables makes full injection infeasible at scale (per industry research).
5. **4-week time-box, 4 milestones** — Resolution of inbox "待解决问题 #6": aligned with "方案 C 工作量=中" and the prototype-scope constraint.
6. **80% accuracy threshold** — Industry research positioned this as "mid-to-upper" for small/single-DB scope; realistic for a 30-question curated demo set, not for enterprise-scale (>50 tables).
7. **No front-end chart rendering** — Resolution of inbox "待解决问题 #5": SDK returns structured data only; host app renders. Closes the open question definitively.
8. **Multi-model routing included** — Haiku 4.5 for simple questions cuts cost ~30×; the router adds minimal complexity and is a quantifiable data point for the metrics report.

### Open Items Deferred to Stage 7 PLAN

- Exact question set content (30 questions) — to be drafted in PLAN stage with input from demo schema.
- Router heuristic thresholds (token count, keyword list) — to be tuned during W3.
- Concrete redaction regex set — defaults shipped, configurable via Settings.
- CI workflow (`.github/workflows/`) — out of RFC scope; will be added in PLAN.

### Risk Register

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Anthropic API rate limits during eval | Medium | Medium | Cache LLM responses in eval; respect 429 |
| 80% accuracy not reachable on demo set | Medium | High | Fall back to easier question set; document gap in metrics report; do not lower threshold silently |
| sqlglot mis-parses valid SQL | Low | High | Fallback path: if `parse_one` fails, log + reject SQL (fail-closed) |
| Worktree tooling flakiness (`EnterWorktree` ERR_STREAM_PREMATURE_CLOSE observed) | High | Low | Workaround: absolute-path operations in worktree; commit/push via `git -C` |
| 4-week time-box overrun | Medium | Medium | Milestone gates with explicit deliverables; if W2 overruns, narrow demo question set before adding features |

### References

- Stage 1 Agent 1 report (project current-state audit)
- Stage 1 Agent 2 report (industry best-practices 2026, including Spider 2.0 / BIRD leaderboard, framework comparison, schema injection tiers)
- inbox/2026-06-15-data-analyst-agent.md (brainstorm source)
- [Anthropic tool use overview](https://platform.claude.com/docs/en/docs/build-with-claude/tool-use/overview)
- [sqlglot documentation](https://github.com/tobymao/sqlglot)
- [Spider 2.0 paper & leaderboard](https://spider2-sql.github.io/)
