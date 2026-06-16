"""AC-19: Redaction applies 4 default rules on rows; can be disabled."""

from data_analyst_agent.executor.redaction import REDACTION_RULES, redact_rows


def test_phone_redacted() -> None:
    rows = [{"phone": "13812345678"}, {"phone": "19900001111"}]
    out = redact_rows(rows, enabled=True)
    assert all(r["phone"] == "[PHONE]" for r in out)


def test_email_redacted() -> None:
    rows = [{"email": "alice@example.com"}]
    out = redact_rows(rows, enabled=True)
    assert out[0]["email"] == "[EMAIL]"


def test_id_card_redacted() -> None:
    rows = [{"id_card": "110101199003070123"}]
    out = redact_rows(rows, enabled=True)
    assert out[0]["id_card"] == "[ID_CARD]"


def test_credit_card_redacted() -> None:
    rows = [{"cc": "4111111111111111"}]
    out = redact_rows(rows, enabled=True)
    assert out[0]["cc"] == "[CREDIT_CARD]"


def test_disabled_passes_through() -> None:
    rows = [{"phone": "13812345678"}]
    out = redact_rows(rows, enabled=False)
    assert out[0]["phone"] == "13812345678"


def test_redaction_handles_non_string_values() -> None:
    rows = [{"amount": 1234.56, "id": 42}]
    out = redact_rows(rows, enabled=True)
    assert out == rows  # no crash on numeric values


def test_redaction_in_string_within_value() -> None:
    rows = [{"note": "Call 13812345678 for details"}]
    out = redact_rows(rows, enabled=True)
    assert "[PHONE]" in out[0]["note"]
    assert "13812345678" not in out[0]["note"]


def test_four_rules_count() -> None:
    assert len(REDACTION_RULES) == 4
