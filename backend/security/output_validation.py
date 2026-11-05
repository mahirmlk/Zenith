"""Output validation: citations + rendering safety (update.md §6.2 step 5)."""
import re

_CITATION_RE = re.compile(r"\[([A-Za-z0-9_\-:.]+)\]|\(cite:\s*([A-Za-z0-9_\-:.]+)\)")


def validate_citations(output: str, retrieved_ids: set[str]) -> list[str]:
    """Return fabricated citation IDs (must be empty for a valid output)."""
    cited = {a or b for a, b in _CITATION_RE.findall(output or "")}
    return sorted(cited - retrieved_ids)


def sanitize_markdown(text: str) -> str:
    """Strip raw HTML/script tags before rendering."""
    text = re.sub(r"</?script[^>]*>", "", text, flags=re.I)
    text = re.sub(r"on\w+\s*=", "", text, flags=re.I)
    return text
