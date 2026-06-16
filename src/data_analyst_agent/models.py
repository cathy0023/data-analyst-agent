"""Pydantic models for the public API contract (RFC DATA-001 §Public API Contract)."""

from typing import Any, Literal

from pydantic import BaseModel


class TokenUsage(BaseModel):
    input_tokens: int
    output_tokens: int
    total_tokens: int


class AskError(BaseModel):
    kind: Literal[
        "config_error",
        "llm_error",
        "sandbox_rejection",
        "sql_execution_error",
        "timeout_error",
        "max_iterations_exceeded",
        "rate_limited",
    ]
    message: str  # user-facing, Chinese
    transient: bool
    retry_after_ms: int | None = None
    debug: dict[str, Any] = {}


class Answer(BaseModel):
    question: str
    executed_sql: str | None
    rows: list[dict[str, Any]] | None
    column_types: dict[str, str] | None
    summary: str  # Chinese natural-language conclusion
    model_used: str
    tokens: TokenUsage
    latency_ms: float
    iterations: int  # 0..max_iter
    error: AskError | None = None
