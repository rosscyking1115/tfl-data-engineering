"""UTC-aware snapshot coverage calculations for the pipeline-health page."""

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone

SNAPSHOT_DUE_UTC = time(6, 30)


@dataclass(frozen=True)
class SnapshotCoverage:
    expected: tuple[date, ...]
    missing: tuple[date, ...]
    pending: date | None
    coverage: float

    @property
    def covered_days(self) -> int:
        return len(self.expected) - len(self.missing)


def calculate_snapshot_coverage(
    collected: list[date],
    *,
    start_date: date,
    now_utc: datetime,
) -> SnapshotCoverage:
    """Classify snapshots as covered, missing, or pending against the UTC job window."""
    if now_utc.tzinfo is None:
        raise ValueError("now_utc must be timezone-aware")

    now_utc = now_utc.astimezone(timezone.utc)
    today = now_utc.date()
    due_at = datetime.combine(today, SNAPSHOT_DUE_UTC, tzinfo=timezone.utc)
    last_due_day = today if now_utc >= due_at else today - timedelta(days=1)

    if last_due_day < start_date:
        expected: tuple[date, ...] = ()
    else:
        expected = tuple(
            start_date + timedelta(days=offset)
            for offset in range((last_due_day - start_date).days + 1)
        )

    collected_set = set(collected)
    missing = tuple(day for day in expected if day not in collected_set)
    pending = today if today > last_due_day and today not in collected_set else None
    coverage = 1 - len(missing) / max(len(expected), 1)

    return SnapshotCoverage(expected, missing, pending, coverage)
