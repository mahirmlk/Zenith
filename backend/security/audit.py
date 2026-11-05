"""Privacy-safe audit records of security decisions (update.md §6.1).

Logs actor/action/outcome only — never prompts, paper text, or secrets.
"""
import json
import logging

logger = logging.getLogger("zenith.audit")


def audit(actor_id: str | None, action: str, outcome: str, resource_id: str | None = None) -> None:
    logger.info(
        json.dumps(
            {
                "actor": actor_id,
                "action": action,
                "outcome": outcome,
                "resource": resource_id,
            }
        )
    )
