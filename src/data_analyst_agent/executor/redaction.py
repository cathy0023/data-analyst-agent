"""Default redaction rules applied to all rows returned by execute_sql.

Per RFC DATA-001 §Security/Result redaction. Default-on; host apps disable
via Settings(enable_redaction=False).
"""

import re

_REDACTION_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    # China mobile phone: 11 digits starting with 1
    (re.compile(r"\b1[3-9]\d{9}\b"), "[PHONE]"),
    # Email
    (re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b"), "[EMAIL]"),
    # China ID card: 18 digits (last may be X)
    (re.compile(r"\b\d{17}[\dXx]\b"), "[ID_CARD]"),
    # Credit card: 13-16 digits
    (re.compile(r"\b(?:\d[ -]*?){13,16}\b"), "[CREDIT_CARD]"),
]

# Public alias for tests / introspection
REDACTION_RULES = _REDACTION_PATTERNS


def _redact_value(value: object) -> object:
    if not isinstance(value, str):
        return value
    redacted = value
    for pattern, replacement in _REDACTION_PATTERNS:
        redacted = pattern.sub(replacement, redacted)
    return redacted


def redact_rows(
    rows: list[dict[str, object]], *, enabled: bool
) -> list[dict[str, object]]:
    """Apply redaction rules to all string values in all rows.

    Non-string values are passed through unchanged. When enabled=False, the
    input is returned unchanged (defensive copy not made — caller owns rows).
    """
    if not enabled:
        return rows
    return [{k: _redact_value(v) for k, v in row.items()} for row in rows]
