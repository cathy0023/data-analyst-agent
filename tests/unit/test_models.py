"""AC-3: Answer / AskError / TokenUsage Pydantic round-trip."""

from data_analyst_agent.models import Answer, AskError, TokenUsage


def test_token_usage_computes_total() -> None:
    u = TokenUsage(input_tokens=100, output_tokens=50, total_tokens=150)
    assert u.total_tokens == 150


def test_ask_error_minimal() -> None:
    e = AskError(
        kind="config_error",
        message="缺少 ANTHROPIC_API_KEY",
        transient=False,
        retry_after_ms=None,
        debug={},
    )
    assert e.transient is False
    assert e.kind == "config_error"


def test_answer_round_trip_no_error() -> None:
    a = Answer(
        question="上月 GMV？",
        executed_sql="SELECT SUM(gmv) FROM orders WHERE ...",
        rows=[{"sum": 1234.56}],
        column_types={"sum": "numeric"},
        summary="上月 GMV 为 1234.56 元。",
        model_used="claude-sonnet-4-6",
        tokens=TokenUsage(input_tokens=200, output_tokens=80, total_tokens=280),
        latency_ms=1850.0,
        iterations=2,
        error=None,
    )
    serialized = a.model_dump_json()
    restored = Answer.model_validate_json(serialized)
    assert restored == a
    assert restored.rows == [{"sum": 1234.56}]


def test_answer_with_error_partial() -> None:
    a = Answer(
        question="...",
        executed_sql=None,
        rows=None,
        column_types=None,
        summary="无法得出结论",
        model_used="claude-sonnet-4-6",
        tokens=TokenUsage(input_tokens=100, output_tokens=20, total_tokens=120),
        latency_ms=500.0,
        iterations=8,
        error=AskError(
            kind="max_iterations_exceeded",
            message="达到 8 轮上限",
            transient=False,
            retry_after_ms=None,
            debug={},
        ),
    )
    assert a.error is not None
    assert a.error.kind == "max_iterations_exceeded"
    restored = Answer.model_validate_json(a.model_dump_json())
    assert restored.error is not None
    assert restored.error.kind == "max_iterations_exceeded"
