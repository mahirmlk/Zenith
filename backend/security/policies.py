"""Tool/action policy: allowed actions, risk tiers, approvals (update.md §6.4)."""

# action -> (risk_tier, requires_fresh_approval)
TOOL_POLICY: dict[str, tuple[str, bool]] = {
    "read_public_paper": ("low", False),
    "search_project_library": ("low", False),
    "generate_comparison": ("medium", False),
    "generate_implementation_plan": ("medium", False),
    "add_annotation": ("medium", False),
    "connect_external_connector": ("high", True),
    "push_commit": ("high", True),
    "publish_or_share": ("high", True),
    "execute_untrusted_code": ("high", True),
    "delete_project": ("high", True),
    "change_roles": ("high", True),
}

# Tools that must never be callable by an LLM/agent at all.
FORBIDDEN_TOOLS = {"execute_shell", "run_sql", "send_email", "delete_database"}


def tool_requires_approval(action: str) -> bool:
    if action in FORBIDDEN_TOOLS:
        raise PermissionError(f"Tool forbidden: {action}")
    entry = TOOL_POLICY.get(action)
    if entry is None:
        # Deny by default (update.md §0.4).
        raise PermissionError(f"Unknown tool denied by default: {action}")
    return entry[1]
