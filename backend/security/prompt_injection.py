"""Injection detection/annotation — never the sole defence (update.md §6.2).

Flags suspicious instruction patterns in untrusted imported text so
downstream code can treat the span as data. Authorization never depends
on this module.
"""
import re

_PATTERNS = [
    re.compile(r"ignore (all )?(previous|prior) instructions", re.I),
    re.compile(r"system prompt", re.I),
    re.compile(r"you are now", re.I),
    re.compile(r"disregard (the )?(above|previous)", re.I),
    re.compile(r"exfiltrate|send .* to (http|https)", re.I),
]


def scan_untrusted(text: str) -> list[str]:
    """Return matched pattern descriptions (empty = no flags)."""
    hits = []
    for pat in _PATTERNS:
        if pat.search(text or ""):
            hits.append(pat.pattern)
    return hits


def annotate(text: str) -> str:
    """Wrap untrusted text with explicit data boundaries."""
    return f"<untrusted_content>\n{text}\n</untrusted_content>"
