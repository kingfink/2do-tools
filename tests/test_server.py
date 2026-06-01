from datetime import UTC, datetime

from _2do_mcp.server import NULL_DUE_DATE_SENTINEL, _from_2do_timestamp


def test_null_due_date_sentinel_is_treated_as_missing_due_date() -> None:
    assert _from_2do_timestamp(NULL_DUE_DATE_SENTINEL, null_due_date=True) is None


def test_null_due_date_sentinel_is_timestamp_outside_due_date_context() -> None:
    assert _from_2do_timestamp(NULL_DUE_DATE_SENTINEL) == datetime.fromtimestamp(
        NULL_DUE_DATE_SENTINEL,
        UTC,
    )
