"""Per-user daily budget counter (update.md §5.4).

In-process for single-instance; swap for Redis INCR in multi-instance
(the job queue already leans on Redis there).
"""
from collections import defaultdict
from datetime import date

_counts: dict[tuple[str, str], int] = defaultdict(int)


def consume(user_id: str, daily_limit: int) -> bool:
    """True if within budget (and consume one unit)."""
    key = (user_id, date.today().isoformat())
    if _counts[key] >= daily_limit:
        return False
    _counts[key] += 1
    return True


def reset_for_tests() -> None:
    _counts.clear()
