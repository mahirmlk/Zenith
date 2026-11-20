"""Owner-managed project email invitations and authenticated acceptance."""

import logging
from datetime import datetime, timezone
from typing import Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, EmailStr

from dependencies import get_current_user
from routers.projects import _owned_project
from services.project_invitations import (
    InvitationDeliveryError,
    invitation_expiry,
    send_project_invitation,
)
from services.notification_email import confirmed_email
from services.supabase_client import get_supabase

logger = logging.getLogger(__name__)
router = APIRouter(tags=["project invitations"])
projects_router = APIRouter(prefix="/api/projects", tags=["project invitations"])


class ProjectInvitationCreate(BaseModel):
    email: EmailStr
    role: Literal["viewer", "editor"]


class ProjectInvitationResponse(BaseModel):
    id: UUID
    project_id: UUID
    email: EmailStr
    role: Literal["viewer", "editor"]
    status: Literal["pending", "accepted", "revoked", "expired", "delivery_failed"]
    created_at: datetime
    expires_at: datetime


class ReceivedProjectInvitation(BaseModel):
    id: UUID
    project_id: UUID
    project_title: str
    role: Literal["viewer", "editor"]
    expires_at: datetime


def _email_key(value: str) -> str:
    return value.strip().casefold()


def _is_unique_violation(error: Exception) -> bool:
    return str(getattr(error, "code", "")) == "23505"


async def _require_project_owner(
    project_id: str,
    user: dict[str, Any],
    supabase: Any,
) -> dict[str, Any]:
    project = await _owned_project(supabase, project_id, user["user_id"])
    if str(project.get("owner_id")) != str(user["user_id"]):
        raise HTTPException(status_code=403, detail="Only the project owner can manage invitations")
    return project


async def _get_invitation(supabase: Any, project_id: str, invitation_id: UUID) -> dict[str, Any]:
    result = await (
        supabase.table("project_invitations")
        .select("*")
        .eq("id", str(invitation_id))
        .eq("project_id", project_id)
        .maybe_single()
        .execute()
    )
    if not isinstance(result.data, dict):
        raise HTTPException(status_code=404, detail="Invitation not found")
    return result.data


async def _dispatch_invitation(
    supabase: Any,
    invitation: dict[str, Any],
    *,
    actor_id: str,
    action: str,
) -> dict[str, Any]:
    invitation_id = UUID(str(invitation["id"]))
    try:
        await send_project_invitation(
            supabase,
            str(invitation["normalized_email"]),
            invitation_id,
        )
    except InvitationDeliveryError as exc:
        from security.audit import audit

        if exc.existing_account:
            # Existing accounts accept from their authenticated project inbox.
            # Keep this response indistinguishable from an ordinary pending
            # invite; membership is still granted only by the verified-email RPC.
            audit(actor_id, action, "allowed", str(invitation.get("project_id", invitation_id)))
            invitation["email_sent_at"] = None
            return invitation

        audit(actor_id, action, "failed", str(invitation.get("project_id", invitation_id)))
        try:
            await (
                supabase.table("project_invitations")
                .update({"status": "delivery_failed", "email_sent_at": None})
                .eq("id", str(invitation_id))
                .execute()
            )
        except Exception as state_error:
            logger.error(
                "Could not record project invite delivery failure id=%s error_type=%s",
                invitation_id,
                type(state_error).__name__,
            )
        logger.warning("Project invite email delivery failed id=%s", invitation_id)
        raise HTTPException(
            status_code=502,
            detail="Invitation delivery failed. The owner can retry this invitation.",
        ) from None

    sent_at = datetime.now(timezone.utc)
    expires_at = invitation_expiry(sent_at)
    try:
        await (
            supabase.table("project_invitations")
            .update(
                {
                    "status": "pending",
                    "email_sent_at": sent_at.isoformat(),
                    "expires_at": expires_at.isoformat(),
                }
            )
            .eq("id", str(invitation_id))
            .execute()
        )
    except Exception as state_error:
        # The pending row already exists. Do not mark it accepted or create a
        # member if recording delivery state fails after Auth sent the link.
        logger.error(
            "Could not record sent project invite id=%s error_type=%s",
            invitation_id,
            type(state_error).__name__,
        )
        raise HTTPException(status_code=502, detail="Invitation state could not be saved") from None

    from security.audit import audit

    audit(actor_id, action, "allowed", str(invitation.get("project_id", invitation_id)))

    return {
        "id": str(invitation_id),
        "project_id": str(invitation["project_id"]),
        "email": str(invitation["email"]),
        "role": invitation["role"],
        "status": "pending",
        "created_at": invitation.get("created_at") or sent_at.isoformat(),
        "expires_at": expires_at.isoformat(),
        "email_sent_at": sent_at.isoformat(),
    }


@projects_router.post(
    "/{project_id}/invitations",
    status_code=201,
    response_model=ProjectInvitationResponse,
)
async def create_project_invitation(
    project_id: UUID,
    body: ProjectInvitationCreate,
    request: Request,
    user: dict[str, Any] = Depends(get_current_user),
    supabase: Any = Depends(get_supabase),
) -> dict[str, Any]:
    project = await _require_project_owner(str(project_id), user, supabase)
    normalized_email = _email_key(str(body.email))
    if user.get("email") and _email_key(user["email"]) == normalized_email:
        raise HTTPException(status_code=422, detail="The project owner cannot invite themselves")

    now = datetime.now(timezone.utc)
    try:
        existing_result = await (
            supabase.table("project_invitations")
            .select("id,project_id,status,expires_at")
            .eq("normalized_email", normalized_email)
            .in_("status", ["pending", "delivery_failed"])
            .maybe_single()
            .execute()
        )
        existing = existing_result.data
        if isinstance(existing, dict):
            existing_expiry = datetime.fromisoformat(
                str(existing["expires_at"]).replace("Z", "+00:00")
            )
            is_same_project = str(existing.get("project_id")) == str(project_id)
            if existing_expiry > now and not is_same_project:
                raise HTTPException(
                    status_code=409,
                    detail="This address has an active invitation to another project. Have them finish it first.",
                )
            if (
                existing_expiry > now
                and is_same_project
                and existing.get("status") == "pending"
            ):
                raise HTTPException(status_code=409, detail="An invitation is already pending")
            await (
                supabase.table("project_invitations")
                .update({"status": "expired"})
                .eq("id", str(existing["id"]))
                .execute()
            )

        created = (
            await supabase.table("project_invitations")
            .insert(
                {
                    "project_id": str(project_id),
                    "invited_by": user["user_id"],
                    "email": normalized_email,
                    "normalized_email": normalized_email,
                    "role": body.role,
                    "status": "pending",
                    "expires_at": invitation_expiry(now).isoformat(),
                }
            )
            .execute()
        )
        rows = created.data or []
        if not rows or not isinstance(rows[0], dict) or not rows[0].get("id"):
            raise RuntimeError("Invitation insert returned no identity")
        invitation = rows[0]
    except HTTPException:
        raise
    except Exception as storage_error:
        if _is_unique_violation(storage_error):
            raise HTTPException(
                status_code=409,
                detail="This address has an active invitation. Have them finish it first.",
            ) from None
        logger.error(
            "Project invitation could not be stored project_id=%s error_type=%s",
            project_id,
            type(storage_error).__name__,
        )
        raise HTTPException(status_code=500, detail="Invitation could not be created") from None

    invitation["project_id"] = str(project.get("id", project_id))
    return await _dispatch_invitation(
        supabase, invitation, actor_id=user["user_id"], action="project:invite_send"
    )


@router.get(
    "/api/project-invitations/received",
    response_model=list[ReceivedProjectInvitation],
)
async def list_received_project_invitations(
    user: dict[str, Any] = Depends(get_current_user),
    supabase: Any = Depends(get_supabase),
) -> list[dict[str, Any]]:
    """List pending invites matching the current Auth-confirmed email only."""
    try:
        email = await confirmed_email(supabase, str(user["user_id"]))
        if not email:
            return []
        now = datetime.now(timezone.utc)
        invitations_result = await (
            supabase.table("project_invitations")
            .select("id,project_id,role,expires_at")
            .eq("normalized_email", _email_key(email))
            .eq("status", "pending")
            .gt("expires_at", now.isoformat())
            .order("expires_at")
            .limit(50)
            .execute()
        )
        invitations = [
            row for row in (invitations_result.data or [])
            if isinstance(row, dict)
            and row.get("expires_at")
            and datetime.fromisoformat(str(row["expires_at"]).replace("Z", "+00:00")) > now
        ]
        project_ids = list(dict.fromkeys(
            str(row["project_id"]) for row in invitations if row.get("project_id")
        ))
        if not project_ids:
            return []
        projects_result = await (
            supabase.table("projects")
            .select("id,title,deleted_at")
            .in_("id", project_ids)
            .execute()
        )
        projects = {
            str(project["id"]): str(project.get("title") or "Research project")
            for project in (projects_result.data or [])
            if isinstance(project, dict)
            and project.get("id")
            and project.get("deleted_at") is None
        }
        return [
            {
                "id": row["id"],
                "project_id": row["project_id"],
                "project_title": projects[str(row["project_id"])],
                "role": row["role"],
                "expires_at": row["expires_at"],
            }
            for row in invitations
            if str(row.get("project_id")) in projects
        ]
    except Exception as error:
        logger.error("Received project invitation lookup failed error_type=%s", type(error).__name__)
        raise HTTPException(status_code=503, detail="Project invitations are temporarily unavailable") from None


@projects_router.get("/{project_id}/invitations", response_model=list[ProjectInvitationResponse])
async def list_project_invitations(
    project_id: UUID,
    user: dict[str, Any] = Depends(get_current_user),
    supabase: Any = Depends(get_supabase),
) -> list[dict[str, Any]]:
    await _require_project_owner(str(project_id), user, supabase)
    try:
        result = await (
            supabase.table("project_invitations")
            .select("id,project_id,email,role,status,created_at,expires_at")
            .eq("project_id", str(project_id))
            .order("created_at", desc=True)
            .range(0, 99)
            .execute()
        )
        return result.data or []
    except Exception as listing_error:
        logger.error(
            "Project invitation listing failed project_id=%s error_type=%s",
            project_id,
            type(listing_error).__name__,
        )
        raise HTTPException(status_code=500, detail="Invitations could not be listed") from None


@projects_router.post(
    "/{project_id}/invitations/{invitation_id}/resend",
    response_model=ProjectInvitationResponse,
)
async def resend_project_invitation(
    project_id: UUID,
    invitation_id: UUID,
    request: Request,
    user: dict[str, Any] = Depends(get_current_user),
    supabase: Any = Depends(get_supabase),
) -> dict[str, Any]:
    await _require_project_owner(str(project_id), user, supabase)
    invitation = await _get_invitation(supabase, str(project_id), invitation_id)
    status = invitation.get("status")
    if status not in {"pending", "delivery_failed", "expired"}:
        raise HTTPException(status_code=409, detail="This invitation cannot be resent")
    if status == "pending":
        expires_at = datetime.fromisoformat(str(invitation["expires_at"]).replace("Z", "+00:00"))
        if expires_at > datetime.now(timezone.utc):
            raise HTTPException(status_code=409, detail="This invitation is still active")
    try:
        await (
            supabase.table("project_invitations")
            .update(
                {
                    "status": "pending",
                    "expires_at": invitation_expiry().isoformat(),
                    "email_sent_at": None,
                }
            )
            .eq("id", str(invitation_id))
            .execute()
        )
    except Exception as state_error:
        logger.error(
            "Project invitation retry state failed id=%s error_type=%s",
            invitation_id,
            type(state_error).__name__,
        )
        raise HTTPException(status_code=500, detail="Invitation could not be retried") from None
    return await _dispatch_invitation(
        supabase, invitation, actor_id=user["user_id"], action="project:invite_resend"
    )


@projects_router.delete("/{project_id}/invitations/{invitation_id}")
async def revoke_project_invitation(
    project_id: UUID,
    invitation_id: UUID,
    user: dict[str, Any] = Depends(get_current_user),
    supabase: Any = Depends(get_supabase),
) -> dict[str, str]:
    await _require_project_owner(str(project_id), user, supabase)
    invitation = await _get_invitation(supabase, str(project_id), invitation_id)
    if invitation.get("status") not in {"pending", "delivery_failed"}:
        raise HTTPException(status_code=409, detail="This invitation cannot be revoked")
    try:
        await (
            supabase.table("project_invitations")
            .update({"status": "revoked"})
            .eq("id", str(invitation_id))
            .execute()
        )
    except Exception as state_error:
        logger.error(
            "Project invitation revocation failed id=%s error_type=%s",
            invitation_id,
            type(state_error).__name__,
        )
        raise HTTPException(status_code=500, detail="Invitation could not be revoked") from None
    from security.audit import audit

    audit(user["user_id"], "project:invite_revoke", "allowed", str(project_id))
    return {"status": "revoked"}


@router.post("/api/project-invitations/{invitation_id}/accept")
async def accept_project_invitation(
    invitation_id: UUID,
    request: Request,
    user: dict[str, Any] = Depends(get_current_user),
    supabase: Any = Depends(get_supabase),
) -> dict[str, Any]:
    """Atomically verify invitee identity, grant membership, and accept invite."""
    try:
        response = await supabase.rpc(
            "accept_project_invitation",
            {
                "p_invitation_id": str(invitation_id),
                "p_accepting_user_id": user["user_id"],
            },
        ).execute()
        result = response.data
        if isinstance(result, list) and result:
            result = result[0]
        if not isinstance(result, dict):
            raise RuntimeError("Invitation RPC returned an invalid response")
    except Exception as rpc_error:
        from security.audit import audit

        audit(user["user_id"], "project:invite_accept", "failed", str(invitation_id))
        logger.error(
            "Project invitation acceptance failed id=%s error_type=%s",
            invitation_id,
            type(rpc_error).__name__,
        )
        raise HTTPException(status_code=500, detail="Invitation could not be accepted") from None

    status = result.get("status")
    if status in {"not_found", "email_mismatch", "email_unverified", "inactive_project"}:
        from security.audit import audit

        audit(user["user_id"], "project:invite_accept", "denied", str(invitation_id))
        raise HTTPException(status_code=404, detail="Invitation not found or unavailable")
    if status in {"expired", "revoked", "delivery_failed"}:
        from security.audit import audit

        audit(user["user_id"], "project:invite_accept", "denied", str(invitation_id))
        raise HTTPException(status_code=410, detail="Invitation is no longer active")
    if status != "accepted":
        logger.error("Invitation RPC returned unexpected status=%s id=%s", status, invitation_id)
        raise HTTPException(status_code=500, detail="Invitation could not be accepted")

    from security.audit import audit

    audit(user["user_id"], "project:invite_accept", "allowed", str(result.get("project_id", "")))
    return result


router.include_router(projects_router)
