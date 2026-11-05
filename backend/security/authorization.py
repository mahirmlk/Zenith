"""Resource + membership authorization (update.md §5.2, §6.1).

Identity (JWT `sub`) is separate from permission: every check here compares
the authenticated user against the resource owner/members. A caller-supplied
`user_id`/role in a request body is never trusted.
"""
from typing import Optional

ROLES = ("owner", "editor", "viewer")


def can_access_run(run_owner: Optional[str], requester: str) -> bool:
    """Deny by default: ownerless runs (anonymous-era or orphaned by
    account deletion) are NOT accessible. Owned runs only by owner."""
    return run_owner is not None and run_owner == requester


def can_access_project(owner_id: str, member_roles: dict[str, str], requester: str) -> bool:
    return owner_id == requester or requester in member_roles


def can_write_project(owner_id: str, member_roles: dict[str, str], requester: str) -> bool:
    if owner_id == requester:
        return True
    return member_roles.get(requester) in ("owner", "editor")


def require_run_access(run_owner: Optional[str], requester: str) -> None:
    if not can_access_run(run_owner, requester):
        # 404 semantics at the router layer (don't leak existence).
        raise PermissionError("Run not found or expired")
