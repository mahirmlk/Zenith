"""Sandbox runner stub (update.md §11).

Execution of untrusted paper code is OFF by default and requires a
separately reviewed isolated runner (no prod secrets, egress
allowlist, CPU/GPU/time caps, non-root). Until that infrastructure
exists, this module refuses all execution.
"""


def run_in_sandbox(*args, **kwargs) -> dict:
    return {
        "status": "not attempted",
        "reason": "Sandbox infrastructure not yet reviewed/deployed — planning only.",
    }
