"""Trusted Supabase Auth operations for project invitations."""
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode, urlsplit
from uuid import UUID

from config import get_settings

INVITATION_TTL = timedelta(hours=1)
INVITATION_ACCEPT_PATH = "/projects/invitations/accept"


class InvitationDeliveryError(RuntimeError):
    """A sanitized Auth Admin invite failure."""

    def __init__(self, *, existing_account: bool = False) -> None:
        super().__init__("Invitation email could not be sent")
        self.existing_account = existing_account


def invitation_expiry(now: datetime | None = None) -> datetime:
    current = now or datetime.now(timezone.utc)
    return current + INVITATION_TTL


def invitation_redirect_url(invitation_id: UUID) -> str:
    """Build a fixed callback from APP_URL; callers cannot supply a redirect."""
    app_url = get_settings().app_url.strip().rstrip("/")
    parsed = urlsplit(app_url)
    settings = get_settings()
    is_local = parsed.hostname in {"localhost", "127.0.0.1", "::1"}
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.netloc
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError("APP_URL must be an http(s) base URL")
    if settings.app_env == "production" and parsed.scheme != "https":
        raise ValueError("APP_URL must use HTTPS in production")
    if parsed.scheme == "http" and not is_local:
        raise ValueError("APP_URL may use HTTP only on localhost")
    return f"{app_url}{INVITATION_ACCEPT_PATH}?{urlencode({'invitation_id': str(invitation_id)})}"


def _is_existing_account_error(exc: Exception) -> bool:
    code = str(getattr(exc, "code", "")).lower()
    message = str(exc).lower()
    return code in {"email_exists", "user_already_exists"} or any(
        marker in message for marker in (
            "email address already exists", "email already exists", "user already exists",
            "user already registered", "already registered",
        )
    )


async def send_project_invitation(
    supabase: object,
    email: str,
    invitation_id: UUID,
) -> None:
    """Send Supabase's invitation email using the server-only Auth Admin API."""
    try:
        auth = getattr(supabase, "auth")
        admin = getattr(auth, "admin")
        await admin.invite_user_by_email(
            email,
            options={"redirect_to": invitation_redirect_url(invitation_id)},
        )
    except Exception as exc:
        raise InvitationDeliveryError(existing_account=_is_existing_account_error(exc)) from None
