from datetime import date, datetime, timezone

import pytest
from snapshot_coverage import calculate_snapshot_coverage


def test_today_is_pending_before_daily_snapshot_is_due():
    collected = [
        date(2026, 7, 8),
        date(2026, 7, 9),
        date(2026, 7, 10),
        date(2026, 7, 13),
    ]

    status = calculate_snapshot_coverage(
        collected,
        start_date=date(2026, 7, 8),
        now_utc=datetime(2026, 7, 14, 6, 29, tzinfo=timezone.utc),
    )

    assert status.expected[-1] == date(2026, 7, 13)
    assert status.missing == (date(2026, 7, 11), date(2026, 7, 12))
    assert status.pending == date(2026, 7, 14)
    assert status.coverage == pytest.approx(4 / 6)


def test_today_is_missing_after_daily_snapshot_window_has_passed():
    collected = [
        date(2026, 7, 8),
        date(2026, 7, 9),
        date(2026, 7, 10),
        date(2026, 7, 13),
    ]

    status = calculate_snapshot_coverage(
        collected,
        start_date=date(2026, 7, 8),
        now_utc=datetime(2026, 7, 14, 6, 30, tzinfo=timezone.utc),
    )

    assert status.expected[-1] == date(2026, 7, 14)
    assert status.missing == (
        date(2026, 7, 11),
        date(2026, 7, 12),
        date(2026, 7, 14),
    )
    assert status.pending is None
    assert status.coverage == pytest.approx(4 / 7)
