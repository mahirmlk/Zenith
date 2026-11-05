"""Entry / tool-call / output enforcement (update.md §6.2).

All checks are deterministic trusted code. Model-based classifiers may
flag content for review but are never authorization authorities.
"""
from security.audit import audit
from security.output_validation import validate_citations
from security.policies import tool_requires_approval


def check_tool_call(action: str, actor_id: str, approved: bool = False) -> None:
    """Raise PermissionError unless the tool call is allowed + approved."""
    try:
        needs_approval = tool_requires_approval(action)
    except PermissionError:
        audit(actor_id, f"tool:{action}", "denied")
        raise
    if needs_approval and not approved:
        audit(actor_id, f"tool:{action}", "approval_required")
        raise PermissionError(f"Fresh user approval required for: {action}")
    audit(actor_id, f"tool:{action}", "allowed")


def check_output(output: str, retrieved_ids: set[str], actor_id: str | None = None) -> None:
    """Reject outputs containing fabricated citation IDs."""
    fabricated = validate_citations(output, retrieved_ids)
    if fabricated:
        audit(actor_id, "output_citations", "rejected", ",".join(fabricated))
        raise ValueError(f"Fabricated citation IDs: {fabricated}")
    audit(actor_id, "output_citations", "allowed")
