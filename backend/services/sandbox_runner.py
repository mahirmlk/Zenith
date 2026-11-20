"""Fail-closed paper-code execution boundary (update.md §11).

There is no reviewed disposable runner in this deployment. This module must
not execute source code, even if a stale or misconfigured environment variable
tries to enable it. Replace this refusal only alongside an independently
reviewed isolation implementation and its security tests.
"""


def sandbox_enabled() -> bool:
    """Execution is unavailable until a reviewed isolated runner exists."""
    return False


def run_in_sandbox(
    paper_id: str = "", code: str = "", timeout_seconds: int = 120
) -> dict[str, str]:
    del paper_id, code, timeout_seconds
    return {
        "status": "not attempted",
        "reason": "No reviewed isolated execution runner is configured; planning only.",
    }
