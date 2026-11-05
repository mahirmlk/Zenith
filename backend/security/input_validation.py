"""Typed input constraints + URL restrictions (update.md §6.1)."""
from services.ssrf import validate_public_url  # noqa: F401  (re-exported)

MAX_QUERY_LEN = 500
MAX_NOTE_LEN = 20000
MAX_INTERESTS = 50


def check_length(value: str, max_len: int, field: str) -> str:
    if len(value or "") > max_len:
        raise ValueError(f"{field} exceeds {max_len} chars")
    return value
