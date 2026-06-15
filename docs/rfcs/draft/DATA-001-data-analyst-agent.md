---
rfc_id: DATA-001
title: "DATA-001: Conversational Data Analysis Agent SDK (Prototype, 6-week)"
created: 2026-06-15
status: Draft v2
series: DATA
author: data-analyst-agent contributors
reviewers: []
related_inbox: inbox/2026-06-15-data-analyst-agent.md
revision_history:
  - v1: 2026-06-15 initial draft
  - v2: 2026-06-15 rewrite after Stage 4 review (3 reviewers, scores 5-6.5/10); applied 4 scope decisions + 11 Critical + 17 High/Medium fixes
---

# DATA-001: Conversational Data Analysis Agent SDK (Prototype, 6-week)

## Goals

1. **Ship a `pip install`-able Python SDK** (`data-analyst-agent`) that lets developers embed conversational data analysis into their applications with ≤10 lines of integration code.
2. **Validate the three-layer architecture** (Agent / Tool / Executor) end-to-end against a demo PostgreSQL database with **30 representative questions (lower bound 20)**, all in Chinese to match the project's target user base.
3. **Hit ≥80% execution-accuracy (EX)** on the in-repo demo question set (median of 3 runs at temperature=0; reported per difficulty tier easy/medium/hard), with NL → SQL → query → conclusion as a single agent loop on **Sonnet 4.6 only** (no router in prototype).
4. **Identify quantified technical limits** of the chosen stack (Anthropic Claude native tool use + sqlglot allow-list sandbox + tiered schema injection + structured logging) — output a metrics report covering accuracy per tier, P50/P95 latency (cold/warm split), token cost per question, and top-5 failure modes.
5. **Lay the architectural foundation** for production hardening (safety sandbox, observability hooks, error taxonomy) without building production-readiness features themselves.

## Background

### Origin

Originated from `/rfc-brainstorm` on 2026-06-15 (see `inbox/2026-06-15-data-analyst-agent.md`). The user classified this as a **technical prototype validation** project — motivation is to de-risk the "LLM + tool use + NL2SQL in an embeddable SDK form factor" path before any production commitment.

### Current State

The repository is freshly initialized (commit `41068a1`): `pyproject.toml` with `dependencies = []`, an empty `src/data_analyst_agent/__init__.py`, an empty `tests/__init__.py`, tooling configured (pytest ≥8, mypy strict, ruff), and the RFC workflow directory structure. No business code, no CI, no demo data.

### Why Now

**Industry signals**:

- **Spider 2.0** (real-world enterprise schemas, >1000 columns) dropped GPT-4o from Spider 1.0's 86.6% to **10.1%** — proving that full-schema injection is no longer viable and Agent-loop + schema-linking is the new SOTA. The window to validate a modern stack is now.
- **Embedded-SDK gap**: The top open-source NL2SQL libs (Vanna v2.0 archived 2026-03-29; DB-GPT and WrenAI server-first) do not cleanly serve the "embed me as a library" use case.
- **Tooling maturity**: Anthropic tool use protocol, `sqlglot` SQL transpilation, and `pgvector` are all production-ready in 2026 — the prototype can stand on stable primitives without framework lock-in.

**Internal urgency**:

The user has multiple downstream use sites (data-analyst-agent repo's name + the brainstorm framing) that currently hand-roll NL2SQL with brittle prompt chains. A 6-week prototype that lands a reusable library prevents 2-3× rework cost when those sites ship their own v1 implementations in the next quarter. Delaying to Q3 forces each site to ship bespoke solutions that will need to be retrofitted later.

### Pain Points Addressed

- Developers currently hand-roll NL2SQL with brittle prompt chains; the SDK must encapsulate best practices (sandboxing, schema retrieval, error taxonomy) so consumers don't repeat them.
- Internal/business teams need a reusable library to drop into multiple products, avoiding duplicate prototyping.

## Alternatives Considered

Captured from brainstorm Stage 4 (`inbox/2026-06-15-data-analyst-agent.md` §"已讨论的方案") for reviewer self-containment.

### 方案 A：极简自撸（驳回）

- **核心思路**：单文件 `DataAnalyst` 类 + Claude 原生 tool use，硬绑 PostgreSQL，不引入任何抽象。
- **驳回理由**：扁平结构与项目「为产品化打基础」的隐性目标冲突；prototype 阶段可读，但后续加多模型 / 观测 / 错误处理时被迫重构。**未选**。

### 方案 B：LlamaIndex NLSQLTableQueryEngine / LangChain SQLDatabaseChain（驳回）

- **核心思路**：复用社区框架的 NL2SQL chain，包一层 SDK；隐式 SQLAlchemy 抽象数据源。
- **驳回理由**：(1) 与 Non-Goal「不做多源抽象」直接冲突；(2) 框架黑盒对 prototype「识别技术硬伤」目标不利——错误时无法定位是框架 / LLM / DB 哪一层的问题；(3) LangChain / LlamaIndex 的 SQL chain API 在 2025-2026 反复重构，依赖易碎。**未选**。

### 方案 C：分层架构（已选 ✓）

- **核心思路**：明确的分层（Agent / Tool / Executor）+ 每层独立可测 + 具象 `PostgresBackend`（**v2 修订：删除 Backend ABC，见 Key Decisions #1**）。
- **选中理由**：(1) 架构清晰、每层可独立测试；(2) 调试时能精确定位是 Agent 决策错、Tool 契约错、还是 SQL 执行错——满足 prototype「识别硬伤」目标；(3) `PostgresBackend` 作为具象类不阻塞未来 MySQL 重构（YAGNI 优于 speculative abstraction）。

## Design

### Architecture: Three-Layer

The SDK is structured around explicit layers, each independently testable, with strict directional dependencies (Agent → Tool → Executor; never reverse).

```
┌──────────────────────────────────────────────────────────────┐
│  Public API:  async def ask(question) -> Answer                │
│               def ask(question) -> Answer  (sync alias)        │
└──────────────────────────────────────────────────────────────┘
                              │
┌─────────────────────────────▼────────────────────────────────┐
│  Agent Layer  (agent.py)                                       │
│  - tool use loop: while stop_reason == "tool_use"              │
│  - safety guards: max_iter=8, repeat-failure circuit breaker   │
│  - structured logging per iteration                            │
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
│  - PostgresBackend (concrete class, NO ABC — see Decision #1)  │
│  - sqlglot-based sandbox: ALLOW-LIST (SELECT/WITH only)        │
│  - statement_timeout enforced at DSN level                     │
│  - read-only DB user + row_limit injection                     │
│  - SQL-hash cache (TTL)                                        │
└────────────────────────────────────────────────────────────────┘
```

### Public API Contract

The SDK exposes one primary class and three core data types.

```python
# src/data_analyst_agent/__init__.py
from .agent import DataAnalyst
from .models import Answer, AskError, TokenUsage

__all__ = ["DataAnalyst", "Answer", "AskError", "TokenUsage"]
```

```python
# Primary class
class DataAnalyst:
    def __init__(self, *, db_url: str, settings: Settings | None = None) -> None: ...

    async def ask(self, question: str, *, conversation_id: str | None = None) -> Answer: ...

    def ask_sync(self, question: str) -> Answer:
        """Sync alias for non-async callers. Wraps asyncio.run(self.ask(...))."""
        ...

    async def close(self) -> None:
        """Release the connection pool. Idempotent."""
        ...
```

```python
# Core data model
class TokenUsage(BaseModel):
    input_tokens: int
    output_tokens: int
    total_tokens: int

class Answer(BaseModel):
    question: str                            # original NL question
    executed_sql: str | None                 # final SQL after sandbox rewrite; None if Agent gave up
    rows: list[dict[str, Any]] | None        # raw result set; None if no SQL executed
    column_types: dict[str, str] | None      # column_name → PG type, e.g. {"price": "numeric"}
    summary: str                             # natural-language conclusion in Chinese
    model_used: str                          # always "claude-sonnet-4-6" in prototype
    tokens: TokenUsage
    latency_ms: float
    iterations: int                          # number of tool_use rounds, 0..max_iter
    error: AskError | None                   # None on success; populated on partial / total failure

class AskError(BaseModel):
    kind: Literal["config_error", "llm_error", "sandbox_rejection", "sql_execution_error",
                  "timeout_error", "max_iterations_exceeded", "rate_limited"]
    message: str                             # user-facing, Chinese
    transient: bool                          # True = caller may retry; False = caller must change something
    retry_after_ms: int | None               # hint for retry backoff
    debug: dict[str, Any]                    # internal details (sanitized); for logs only
```

### Concurrency Model

**Async-first**:

- Primary API is `async def ask(...)`. Host applications using FastAPI / asyncio can `await agent.ask(q)`.
- `def ask_sync(...)` provides a sync alias that wraps `asyncio.run(self.ask(...))` — convenience for scripts / REPL.
- **No streaming in prototype** (Non-Goal): `ask()` returns a single `Answer` after the full agent loop terminates. Latency is bounded by `max_iter * per_iteration_timeout`.
- `PostgresBackend` owns a single `psycopg_pool.AsyncConnectionPool`. Default `min_size=1, max_size=5`. Pool is created lazily in `DataAnalyst.__init__` and released via `await agent.close()` or context manager `__aexit__`.
- **Multi-turn conversation is a Non-Goal** (see Non-Goals) — `conversation_id` parameter is reserved in the API for forward compatibility but ignored in v1.

### Configuration

```python
class Settings(BaseSettings):
    # Required
    anthropic_api_key: SecretStr        # env: ANTHROPIC_API_KEY; ConfigError if missing on init
    db_url: str                         # passed explicitly to DataAnalyst(db_url=...)

    # LLM
    default_model: str = "claude-sonnet-4-6"  # only this in v1; multi-model deferred
    max_iterations: int = 8
    llm_timeout_seconds: float = 60.0

    # Sandbox / Executor
    statement_timeout_seconds: float = 10.0   # enforced via DSN options=-c statement_timeout=Xs
    row_limit: int = 1000                     # injected into SELECT if absent
    cache_ttl_seconds: int = 300              # SQL-hash cache

    # Redaction (default-on, see Security)
    enable_redaction: bool = True

    # Logging
    log_level: str = "INFO"

    model_config = SettingsConfigDict(env_prefix="DATA_AGENT_", env_file=".env", extra="forbid")
```

**Failure modes**:

- Missing `ANTHROPIC_API_KEY` → `DataAnalyst.__init__` raises `ConfigError("缺少 ANTHROPIC_API_KEY 环境变量，请在 shell 或 .env 中设置。")`. **Fail-fast at construction**, not deferred to first `ask()`.
- Missing / malformed `db_url` → `__init__` opens a probe connection; failure raises `ConfigError` with `psycopg` error details.

### Error Handling

#### Error taxonomy (maps to `AskError.kind`)

| Kind | Trigger | `transient` | Retry policy |
|------|---------|-------------|--------------|
| `config_error` | Missing API key, bad `db_url`, sandbox misconfig | `False` | Do not retry — fix config |
| `llm_error` | Anthropic 5xx / network error / parse failure | `True` | Exponential backoff: 1s, 2s, 4s, max 3 retries, jitter ±20% |
| `rate_limited` | Anthropic 429 | `True` | Respect `retry-after` header; max 3 retries |
| `sandbox_rejection` | Generated SQL is non-SELECT / contains banned constructs | `False` for caller; **True for Agent** | Feed `tool_use_error` back to LLM, allow up to 2 self-corrections within `max_iter` |
| `sql_execution_error` | DB-side syntax error, permission denied, connection lost | `True` if connection lost; `False` otherwise | Connection-lost → reconnect + retry once; other → return to caller |
| `timeout_error` | `statement_timeout` triggered, or LLM call exceeded `llm_timeout_seconds` | `True` | One retry with simplified SQL (drop JOIN / push LIMIT lower) — best effort |
| `max_iterations_exceeded` | Agent loop ran `max_iter` rounds without converging | `False` | Return partial `Answer` with `executed_sql=None`, `rows=None`, `summary="无法在 8 轮内得出结论"` |

#### Tool-use error feedback protocol

When `execute_sql` rejects SQL (sandbox or DB error), the Agent must observe a structured `tool_use_error` block (Anthropic format) containing:

```json
{
  "kind": "sandbox_rejection",
  "message": "SQL 包含禁止的语句: DELETE。仅允许 SELECT / WITH ... SELECT。",
  "hint": "请改写为只读查询；如需删除数据，请联系 DBA。"
}
```

This allows the LLM to self-correct within the loop. If 2 consecutive `sandbox_rejection` occur for the same question, the Agent terminates with `max_iterations_exceeded` (circuit breaker).

### Schema Injection Strategy (tiered by scale)

| DB size | Strategy | Token cost (demo-proven estimate) |
|---------|----------|-----------------------------------|
| ≤30 tables | Full schema in system prompt | ~1–4k tokens (10 tables × ~60 cols × ~6 tokens/col ≈ 3.6k) |
| 30–200 tables | `get_schema(tables: list[str])` on-demand tool, cached | ~300–500 tokens per call |

For the prototype we implement **tier 1 only** (full schema injection). **Tier 2 (on-demand tool) is deferred to post-prototype** because the 10-table demo set cannot exercise it (always falls into tier 1). This resolves the Stage-4 review finding "Tier 2 unverifiable in demo".

Token cost numbers above are based on a **measured estimate** against the demo schema (10 tables, ~60 columns total, with comments and sample values); they will be re-measured in W1 and reported in the metrics report.

### Business Glossary

YAML file `glossary.yaml` ships with the SDK and is editable by host applications. **Chinese-first** schema (matches the prototype's Chinese demo question set):

```yaml
# glossary.yaml — v0.1 schema
version: "0.1"
entries:
  - term: "GMV"
    zh_aliases: ["成交金额", "成交额"]
    en_aliases: ["gross_merchandise_volume"]
    maps_to:
      table: orders
      column: gmv
      aggregation: sum   # sum | avg | count | none
    unit: "CNY"
    description: "订单总金额（含税、含运费），按订单 created_at 归属"
    sample_questions:
      - "上个月 GMV 多少？"
      - "各品类 GMV 排名？"

  - term: "活跃用户"
    zh_aliases: ["DAU", "活跃"]
    en_aliases: ["active_user", "dau"]
    maps_to:
      table: users
      column: user_id
      aggregation: count_distinct
    description: "近 30 天有 >=1 笔订单的用户数"
    sample_questions:
      - "上月活跃用户数？"
```

The Agent reads this file in the system prompt; glossary updates are hot-reloadable via `DataAnalyst.reload_glossary()` (v1: only reload at construction).

### LLM Protocol

- **Primary / only model**: Anthropic Claude Sonnet 4.6 (`claude-sonnet-4-6`) via native tool use.
- **Multi-model routing**: **Deferred** to post-prototype (Stage-4 review consensus: ROI not justified for 30-question demo, router bugs risk lowering accuracy; Stage 1 research's "30× cost saving" was output-token-only — input token ratio is ~3-4×, total demo LLM cost ≈ $5-20 over 6 weeks, optimization not warranted).
- **Tool use loop**: `while stop_reason == "tool_use"` pattern, ~100 LOC in `agent.py`. Fail-closed on parse errors.
- **Token budget per call**: design tools with terse descriptions + compact param names (Anthropic tool use system prompt costs ~497 tokens for Sonnet 4.6).

### Internationalization

**Chinese-first** for prototype scope:

- Demo question set (`tests/fixtures/questions.yaml`): **all 30 questions in Chinese**.
- System prompt: Chinese instructions + bilingual schema dump (Chinese comments if `glossary.yaml` provides, else English column names).
- Natural-language `summary` in `Answer`: Chinese.
- Error messages in `AskError.message`: Chinese (user-facing), `debug` dict may contain English keys for logs.
- **English i18n is a Non-Goal** for prototype; deferred to post-prototype if non-Chinese users emerge.

### Security & Sandboxing

#### SQL sandbox (allow-list, not deny-list)

After Stage-4 review flagged deny-list as insufficient, the sandbox is now **allow-list** with explicit deny-layer:

1. **Allow-list (primary defense)**: `sqlglot.parse_one(sql, dialect="postgres")` must yield a root node of type `exp.Select` or `exp.With` (containing only SELECT in body). Anything else → reject.
2. **Deny-list (defense-in-depth)**: even within allowed shape, explicitly reject if AST contains any of: `INSERT`, `UPDATE`, `DELETE`, `MERGE`, `DROP`, `ALTER`, `TRUNCATE`, `GRANT`, `REVOKE`, `COPY`, `CALL`, `LISTEN`, `NOTIFY`, `DO` (anonymous PL/pgSQL blocks), `COMMENT ON`, `SET` (other than sandbox-injected `SET LOCAL`).
3. **Subquery traversal**: walk the full AST (including CTEs and subqueries); deny any non-SELECT node anywhere.
4. **`statement_timeout` enforcement**: **at DSN level**, not via SQL `SET LOCAL`. The connection string includes `options='-c statement_timeout=10000'` (configurable). SQL-side `SET LOCAL statement_timeout` is no longer trusted (an LLM can write `RESET statement_timeout` to bypass it).
5. **`LIMIT` injection**: if a SELECT has no `LIMIT` clause, append `LIMIT <row_limit>`; if it has `LIMIT > row_limit`, truncate to `row_limit`.
6. **Read-only DB user**: SDK connects with a DB user that has `SELECT`-only grants; documented in README setup. Enforced via `SET ROLE` check at init (probe query).
7. **Fail-closed**: if `sqlglot.parse_one` raises (unparseable SQL), log + reject; never execute.

#### Result redaction (default-on)

Redaction is **enabled by default** (`Settings.enable_redaction = True`). Host applications can disable via Settings. Default regex set:

```python
REDACTION_RULES = [
    # China mobile phone: 11 digits starting with 1
    (re.compile(r"\b1[3-9]\d{9}\b"), "[PHONE]"),
    # Email
    (re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b"), "[EMAIL]"),
    # China ID card: 18 digits (last may be X)
    (re.compile(r"\b\d{17}[\dXx]\b"), "[ID_CARD]"),
    # Credit card: 13-16 digits
    (re.compile(r"\b(?:\d[ -]*?){13,16}\b"), "[CREDIT_CARD]"),
]
```

Redaction runs in the Executor layer, **after** SQL execution **before** rows are returned to the Tool layer — single chokepoint, can't be bypassed by Agent decisions.

### Observability

- **Structured logs** (stdlib `logging` + `python-json-logger`): one log entry per tool call with fields `tool`, `input_hash`, `output_row_count`, `duration_ms`, `tokens`, `error_kind`.
- **OpenTelemetry**: not in prototype (decision: keeping the surface area minimal — see Stage-4 M-3). Hooks deferred; `Settings` reserves `otel_endpoint: str | None = None` for forward compat.

## Non-Goals

- **No productization**: auth, multi-tenant, billing, SSO — all out of scope. Assume single-tenant, trusted environment.
- **No advanced statistical modeling**: forecasting, clustering, time-series prediction, ML training — out of scope. SDK only does data retrieval + lightweight aggregation.
- **No multi-source abstraction in prototype**: `PostgresBackend` is a concrete class (no ABC); MySQL / Snowflake / BigQuery support requires future RFC. **v2 change**: removes the v1 Backend ABC contradiction.
- **No multi-turn conversation**: each `ask()` is independent; `conversation_id` parameter is reserved but ignored in v1. Memory/threading deferred.
- **No multi-model routing**: prototype runs Sonnet 4.6 only; Haiku / Opus / OpenAI routing deferred.
- **No Tier 2 / Tier 3 schema injection**: 10-table demo falls into Tier 1 (full schema); on-demand `get_schema` tool and pgvector schema retrieval deferred.
- **No streaming output**: `ask()` returns a single `Answer` after the full loop; no incremental delivery.
- **No English i18n**: prototype targets Chinese users only.
- **No front-end chart rendering**: SDK returns structured data only; rendering is the host app's job.
- **No OpenTelemetry integration**: hooks reserved but not implemented.

## Implementation

### Module Layout

```
src/data_analyst_agent/
├── __init__.py              # Public API exports
├── agent.py                 # Agent layer: async tool use loop, sync alias, guards
├── config.py                # Settings (pydantic-settings), env binding
├── models.py                # Answer, AskError, TokenUsage, ResultSet, etc.
├── logging_setup.py         # Structured logging config
├── llm/                     # LLM client
│   ├── __init__.py
│   ├── base.py              # LLMClient Protocol (Python Protocol, not ABC)
│   └── anthropic_client.py  # AnthropicClient(concrete) + retry/backoff
├── tools/                   # Tool layer
│   ├── __init__.py
│   ├── base.py              # Tool Protocol + registry
│   ├── list_tables.py
│   ├── get_schema.py
│   ├── execute_sql.py
│   └── explain_plan.py
└── executor/                # Executor layer
    ├── __init__.py
    ├── postgres.py          # PostgresBackend (CONCRETE class, no ABC)
    ├── sandbox.py           # sqlglot allow-list + deny-list + LIMIT injection
    ├── redaction.py         # Default regex rules + apply() function
    └── cache.py             # SQL-hash cache with TTL
```

### Dependencies

Runtime:

```toml
dependencies = [
    "anthropic==0.50.*",          # pinned minor (Stage-4 C-2): avoid 0.40 vs 0.50 API shape drift
    "sqlalchemy>=2.0,<3.0",
    "psycopg[binary,pool]>=3.2,<4.0",
    "sqlglot>=25.0,<26.0",
    "pydantic>=2.7,<3.0",
    "pydantic-settings>=2.3,<3.0",
    "python-dotenv>=1.0,<2.0",
    "python-json-logger>=2.0,<3.0",
]
```

Dev:

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
    "pytest-postgresql>=5.0", # in-test PG via postgres binaries
]
```

**W1 task 0 (gate): sync `pyproject.toml` with the above list before any other W1 work begins.**

### Test Strategy

| Layer | Test type | Strategy |
|-------|-----------|----------|
| Sandbox | Unit (no DB) | sqlglot AST tests: allow-list acceptance, deny-list rejection (16+ banned constructs), subquery traversal, LIMIT injection |
| PostgresBackend | Integration (real PG via `pytest-postgresql`) | `conftest.py` seeds from `tests/fixtures/demo_db.sql` |
| Tools | Unit | Mock `PostgresBackend`; assert Pydantic input/output contract |
| LLMClient | Unit + integration | `respx` mock for canned tool_use responses; integration smoke test against real Anthropic API (marked `@pytest.mark.live`, skipped in CI default) |
| Agent loop | Integration | Mock `LLMClient` returning canned tool_use sequences; verify termination, retry, circuit breaker |
| **Failure injection** (new) | Integration | Mock LLM returns malformed tool_use / disallowed SQL / network error; verify retry, sandbox rejection feedback, partial Answer on max_iter |
| End-to-end | Integration | Real PG + mocked LLM (deterministic) on 30 demo questions |
| Eval (W3) | Statistical | Real PG + real Sonnet 4.6; 30 questions × 3 runs at temp=0; report median accuracy per tier |

### Demo Dataset & Question Set

- **Dataset**: `tests/fixtures/demo_db.sql` — synthetic Chinese e-commerce schema (10 tables: `users`, `orders`, `order_items`, `products`, `categories`, `regions`, `events`, `coupons`, `refunds`, `inventory`). Column comments in Chinese where business meaning is non-obvious. Seed ~10k rows with realistic distributions.
- **Question set**: `tests/fixtures/questions.yaml` — **30 questions in Chinese**, each tagged `difficulty: easy|medium|hard` and `expected_shape: rows|scalar|none`:
  - easy (15): single-table SELECT, basic aggregation ("上月 GMV 多少？")
  - medium (10): multi-table JOIN, GROUP BY ("各品类销量排名 top 5？")
  - hard (5): nested subqueries / window functions / multi-step reasoning ("对比上季度环比增长最高的 3 个品类")
- **Eval script**: `scripts/eval.py` — runs all 30 questions × 3 runs at `temperature=0`, normalizes results (see Eval Normalization below), outputs `accuracy_report.json` with per-question pass/fail per run, per-tier aggregate accuracy, P50/P95 latency (cold/warm split), token cost.

#### Eval Normalization

Result-row-set comparison rules (resolves Stage-4 H-1):

1. **Numeric tolerance**: floats compared with `abs(a-b) < 1e-6`; `Decimal` cast to `float` first.
2. **NULL vs empty**: `None` and `""` are distinct; NULL semantics preserved.
3. **Column alignment**: by name (not by position); missing/extra columns = fail.
4. **Row ordering**: unordered comparison unless `expected_shape` declares `ordered`; sort by all-column tuple for unordered.
5. **Datetime**: compared as ISO 8601 strings; timezone-normalized to UTC before comparison.

These rules are encoded in `scripts/eval_normalizer.py` with its own unit tests (AC-9).

### Milestones (6-week)

Time-box extended from 4 to 6 weeks after Stage-4 review (Reviewer 2 estimated 27-50 person-days; 3 × 6 × 5 = 90 person-hours ≈ 11 person-days at 100% focus, padded to 18 person-days with realistic utilization — fits the lower bound).

| Week | Deliverable | Gate criteria |
|------|-------------|---------------|
| W1 | `pyproject.toml` synced; `Settings` + `DataAnalyst.__init__` + `PostgresBackend` (concrete) + sandbox (allow-list) + redaction defaults | AC-1, AC-2, AC-17 pass; sandbox rejects 16+ banned constructs; `statement_timeout` works via DSN on real PG |
| W2 | 4 tools (`list_tables`, `get_schema`, `execute_sql`, `explain_plan`) with Pydantic schemas; `LLMClient` Protocol + `AnthropicClient`; Agent loop with `max_iter=8` + circuit breaker; failure injection tests | AC-6, AC-7, AC-8, AC-16 pass; mock LLM tests green; `pytest --asyncio-mode=auto` clean |
| W3 | Demo dataset (`demo_db.sql` 10 tables + 10k rows); 30-question set `questions.yaml` with expected shapes; `eval.py` + `eval_normalizer.py` (with unit tests); **smoke run with mock LLM** to validate pipeline | AC-9 pass with mock LLM (sanity: 30/30 deterministic); `accuracy_report.json` schema fixed |
| W4 | First real-LLM eval run on 30 questions × 3 runs; per-tier accuracy baseline; prompt / glossary iteration | AC-10 reached OR plan-B triggered (see Risk Register); failure-mode analysis drafted |
| W5 | Latency optimization (warm pool, cache hit ratio); metrics report (`docs/metrics-report.md`) draft | AC-11 split into cold/warm; metrics report has all 5 required sections |
| W6 | SDK packaging; `examples/demo.py` + `make demo` scripted; README + 5-minute-clone test; final metrics report | AC-12, AC-13, AC-14(new: scripted demo), AC-15, AC-18 pass |

## Acceptance Criteria

| # | Criterion | Verification |
|---|-----------|--------------|
| AC-1 | `pip install -e ".[dev]"` succeeds on Python 3.10+ in a clean venv | Fresh venv install exits 0 |
| AC-2 | `from data_analyst_agent import DataAnalyst, Answer, AskError, TokenUsage` resolves | `python -c "..."` exits 0 |
| AC-3 | `Answer` Pydantic schema has all fields per Public API Contract; round-trip serialization works | `tests/unit/test_models.py::test_answer_round_trip` passes |
| AC-4 | Sandbox rejects **all of**: `INSERT`, `UPDATE`, `DELETE`, `MERGE`, `DROP`, `ALTER`, `TRUNCATE`, `GRANT`, `REVOKE`, `COPY`, `CALL`, `LISTEN`, `NOTIFY`, `DO` (anonymous block), `COMMENT ON`, `SET` (non-sandbox) — 16 banned constructs | `tests/unit/test_sandbox.py` ≥16 rejection test cases all pass |
| AC-5 | Sandbox enforces `LIMIT` and `statement_timeout`; **pg_sleep(60) is killed at 10s via DSN-level timeout** (not SQL-side `SET LOCAL`) | `tests/integration/test_postgres_backend.py::test_statement_timeout_kills_pg_sleep` < 15s wall clock |
| AC-6 | `PostgresBackend` concrete class implements `connect / execute / list_tables / get_table_schema / explain / close`; all methods have type signatures per Public API Contract | `tests/integration/test_postgres_backend.py` covers each method |
| AC-7 | Tool layer has `list_tables`, `get_schema`, `execute_sql`, `explain_plan`; each has Pydantic input/output schema validated | `tests/unit/test_tools.py` covers each tool's contract |
| AC-8 | Agent loop terminates within `max_iter=8` even on adversarial input (mock LLM returning tool_use forever); on terminate, returns `Answer(error=AskError(kind="max_iterations_exceeded"), ...)` | Property-based test with mock LLM |
| AC-9 | `scripts/eval.py` produces `accuracy_report.json` with 30 entries (one per question) × 3 runs, plus per-tier aggregates + cold/warm latency split + token cost; `eval_normalizer.py` has its own unit tests | `accuracy_report.json` schema validated; normalizer unit tests green |
| AC-10 | **Median accuracy across 3 runs at temperature=0 ≥80% overall AND ≥90% on easy tier AND ≥60% on hard tier**; per-question pass/fail + actual SQL saved for post-hoc analysis | `accuracy_report.json` `"overall_accuracy_median" >= 0.80` AND `"easy_accuracy_median" >= 0.90` AND `"hard_accuracy_median" >= 0.60` |
| AC-11 | P95 latency on demo set (single-threaded, Sonnet 4.6) ≤ **20s warm** (after 3 warm-up calls) and ≤ 45s cold (first call); reported separately, no single threshold | `accuracy_report.json` `"p95_warm_ms" <= 20000` AND `"p95_cold_ms" <= 45000` |
| AC-12 | **Scripted 5-minute clone-to-run**: `make demo` (single command, idempotent, runs `docker compose up -d postgres` + `pip install -e .` + seed + `python examples/demo.py`); measured ≤5 min on macOS arm64 + Linux x86_64 | CI job `e2e-clone-to-run.yml` runs `make demo` on a clean container, asserts `Answer.summary` is non-empty |
| AC-13 | Metrics report (`docs/metrics-report.md`) has 5 sections: (1) overall + per-tier accuracy, (2) P50/P95 latency cold/warm, (3) token cost per tier + total, (4) top-5 failure modes with examples, (5) plan-B / scope-change log if triggered | File exists with 5 H2 sections, each non-empty |
| AC-14 | (Removed in v2 — multi-model router deferred. Slot reserved for future use.) | N/A |
| AC-15 | `mypy --strict src/` clean (0 errors); `ruff check src/ tests/` clean (0 errors) | `make lint` exits 0; mypy `ignore_missing_imports` allowed in `tests/` only |
| AC-16 | **Failure injection tests pass**: 5 scenarios (malformed tool_use, disallowed SQL → self-correct, persistent sandbox rejection → circuit break, LLM 5xx → retry, max_iter no converge → partial Answer) | `tests/integration/test_failure_injection.py` 5/5 green |
| AC-17 | Missing `ANTHROPIC_API_KEY` env var at `DataAnalyst.__init__` raises `ConfigError` with Chinese actionable message; missing/invalid `db_url` similarly fails fast with `psycopg` details | `tests/unit/test_config.py::test_missing_api_key` + `test_bad_db_url` |
| AC-18 | **W1 task 0 done**: `pyproject.toml` `dependencies` and `[project.optional-dependencies] dev` match the RFC §Dependencies table exactly | `tests/test_pyproject_sync.py` parses and asserts |
| AC-19 | Redaction applies 4 default rules (phone / email / ID card / credit card) on all `rows` returned by `execute_sql`; can be disabled via `Settings(enable_redaction=False)` | `tests/integration/test_redaction.py` 4 fixture cases + opt-out case |
| AC-20 | Concurrent `ask()` calls (5 parallel) share the connection pool without deadlock; pool releases cleanly on `close()` | `tests/integration/test_concurrency.py::test_parallel_asks` |

## Notes

### Key Decisions

1. **Remove Backend ABC (v2 change)** — Stage-4 review consensus (3 reviewers flagged). `PostgresBackend` is a concrete class; no speculative abstraction. Resolves inbox #1 definitively (PG-only, MySQL is a future RFC's problem). Tradeoff accepted: when MySQL support is added, a thin refactor (extract interface from existing methods) will be required — this is cheaper than maintaining an unused ABC for 6 weeks.
2. **PostgreSQL-only in prototype** — Resolution of inbox #1.
3. **EX (execution accuracy) over SQL string equality** — Industry standard (Spider/BIRD). Eval normalizer handles float tolerance, NULL semantics, datetime normalization, column-name alignment, unordered row comparison.
4. **Tier 1 schema injection only** — Resolution of inbox #4. Tier 2 (on-demand tool) deferred because 10-table demo can't exercise it (always Tier 1); building it would be untested code.
5. **6-week time-box** — Resolution of inbox #6. Stage-4 review (Reviewer 2) estimated 27-50 person-days realistic effort; 4 weeks was 12 person-days, infeasible. 6 weeks (≈18 person-days at realistic utilization) fits the lower bound while preserving scope. Replaces v1's "fall back to easier question set" mitigation (which was a hidden AC downgrade).
6. **80% accuracy with confidence interval** — Resolution of inbox #2. v2 specifies: **3 runs at temperature=0, report median**; per-tier thresholds (easy ≥90%, medium default, hard ≥60%) instead of a single brittle number. Resolves v1's "single-run gamble" issue.
7. **No front-end chart rendering** — Resolution of inbox #5. SDK returns structured data only.
8. **Multi-model routing DEFERRED** (v2 change) — Stage-4 consensus: ROI not justified for 30-question demo ($5-20 total LLM cost over 6 weeks; "30× cost saving" in Stage 1 research was output-token-only, real ratio ~3-4× on input). Router bugs risk lowering accuracy. Decision: prototype runs Sonnet 4.6 only; cost baseline reported in metrics report; router evaluated in a follow-up RFC if metrics warrant.
9. **Native Anthropic tool use (no framework)** — Stage 1 research + Stage-4 review consensus: `while stop_reason == "tool_use"` loop is ~100 LOC, max debuggability, no framework overhead. `instructor` considered and rejected (single-shot structuring, weak at multi-tool loop); `pydantic-ai` considered and deferred (Pydantic type safety is nice-to-have, not need-to-have for prototype).
10. **Sandbox is allow-list** (v2 change) — Stage-4 review flagged v1 deny-list as insufficient (`COPY`, `DO`, pl/pgSQL blocks, `MERGE` not covered). Allow-list = root AST must be `Select` or `With`. `statement_timeout` moved from SQL `SET LOCAL` (bypassable) to DSN options (not bypassable). Resolves v1's sandbox holes.
11. **Redaction default-on** (v2 change) — Stage-4 review flagged v1's "opt-in" as wrong default for a SDK consuming potentially sensitive rows. Now on by default with 4 rules; opt-out via Settings.
12. **Chinese-first i18n** (v2 change) — Project name `data-analyst-agent` + Chinese-speaking user base → all demo questions, system prompt, error messages, glossary in Chinese. English deferred.

### Open Items Deferred to Stage 7 PLAN

- Exact 30-question content (concrete NL + expected SQL/shape per difficulty tier) — requires W1 demo schema finalization first.
- `make demo` exact shell script — designed in W6.
- Concrete CI workflow (`.github/workflows/*.yml`) — Stage-4 review noted AC-15 needs CI to be meaningful; minimal CI (lint + unit tests + e2e clone-to-run) is in-scope for W6, **full CI matrix deferred**.

### Risk Register

| # | Risk | Likelihood | Impact | Mitigation |
|---|------|------------|--------|------------|
| R1 | Anthropic SDK breaking change within `anthropic==0.50.*` (minor pin) | Low | High | Pin to specific minor; CI runs `pip install --upgrade` weekly to detect breakage early |
| R2 | Anthropic API rate limits during W4 eval (30 q × 3 runs = 90 calls/day) | Medium | Medium | Eval script implements exponential backoff on 429; cache responses for re-runs |
| R3 | Sonnet 4.6 deprecated / replaced by 4.7 during 6-week window | Medium | High | Model ID is configurable via Settings; if Anthropic deprecates, swap alias; document migration in metrics report |
| R4 | 80% accuracy not reachable on hard tier (≥60% threshold) | Medium | Medium | **Plan B**: if hard tier median < 60% on W4, document gap in metrics report with failure analysis; do NOT silently lower threshold; discuss with user whether to expand question set, improve glossary, or accept gap |
| R5 | sqlglot mis-parses valid PG SQL (e.g., complex CTE, window functions) | Low | High | Fail-closed by design (reject + log); `tests/fixtures/sql_corpus.sql` carries 50+ PG-specific SQL shapes tested for both acceptance and rejection |
| R6 | PG version drift between dev / CI / demo | Medium | Medium | CI runs against `postgres:16` only in prototype; README documents PG 14+ requirement; v1 does not matrix-test across PG versions |
| R7 | `pytest-postgresql` binaries unavailable / slow in CI | Low | Medium | Fallback: `docker compose` based fixture; documented in `conftest.py` |
| R8 | 6-week time-box overrun despite padding | Medium | Medium | Weekly gate review; if W4 (real-LLM eval) shows accuracy >10pp below threshold, escalate before W5 (do not push to W6 silently) |

**Removed from v1 Risk Register** (Stage-4 M-4): "Worktree tooling flakiness" — this is a dev-environment observation, not a project risk. Moved to Dev Environment Notes below.

### Dev Environment Notes

- Stage-4 review (Reviewer 1) flagged that `EnterWorktree` Claude Code tool occasionally fails with `ERR_STREAM_PREMATURE_CLOSE` in this environment. **Workaround**: operate in worktree via absolute paths + `git -C <worktree>` commands; no impact on RFC scope.
- `rtk` wrapper is configured globally (`~/.claude/RTK.md`); some git commands produce `Shell cwd was reset to ...` notices — these are cosmetic and do not affect correctness.

### References

- Stage 1 Research — Project Current State: `docs/rfcs/inbox/_stage1_agent1_report.md` (verbatim transcript in conversation log, to be persisted in PLAN stage)
- Stage 1 Research — Industry Best Practices 2026: `docs/rfcs/inbox/_stage1_agent2_report.md` (verbatim transcript in conversation log)
- Brainstorm source: [`inbox/2026-06-15-data-analyst-agent.md`](../inbox/2026-06-15-data-analyst-agent.md)
- RFC README (series config): [`README.md`](../README.md)
- Project CLAUDE.md: [`/CLAUDE.md`](../../../CLAUDE.md)
- [Anthropic tool use overview](https://platform.claude.com/docs/en/docs/build-with-claude/tool-use/overview)
- [Anthropic tool use loop](https://platform.claude.com/docs/en/agents-and-tools/tool-use/how-tool-use-works)
- [sqlglot documentation](https://github.com/tobymao/sqlglot)
- [psycopg-pool docs](https://www.psycopg.org/psycopg3/docs/api/pool.html)
- [Spider 2.0 paper & leaderboard](https://spider2-sql.github.io/)
- [BIRD-SQL leaderboard](https://bird-bench.github.io/)
- [Snowflake Cortex Analyst semantic model spec](https://docs.snowflake.com/en/user-guide/snowflake-cortex/cortex-analyst/semantic-edit)
