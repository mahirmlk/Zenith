from typing import Any

from fastapi import HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jwt.exceptions import InvalidTokenError
from services.jwt_validator import decode_supabase_token

security = HTTPBearer(auto_error=False)


async def _decode_token(token: str) -> dict[str, Any] | None:
    """Decode and validate a Supabase JWT. Returns payload or None."""
    try:
        return await decode_supabase_token(token)
    except InvalidTokenError:
        return None


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
) -> dict[str, Any]:
    if not credentials:
        raise HTTPException(status_code=401, detail="Authorization header missing")

    payload = await _decode_token(credentials.credentials)
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid token")

    # Reject service_role tokens (H3): they must never authenticate as
    # a user. When aud is present it must be "authenticated".
    aud = payload.get("aud")
    if aud:
        audiences = aud if isinstance(aud, list) else [aud]
        if "service_role" in audiences or "authenticated" not in audiences:
            raise HTTPException(status_code=401, detail="Invalid token audience")
    if payload.get("role") == "service_role":
        raise HTTPException(status_code=401, detail="Service role tokens are not user sessions")

    user_id = payload.get("sub")
    if not isinstance(user_id, str) or not user_id:
        raise HTTPException(status_code=401, detail="Invalid token: no subject")
    email = payload.get("email")
    return {"user_id": user_id, "email": email if isinstance(email, str) else None}


async def get_user_id(user: dict[str, Any] = Depends(get_current_user)) -> str:
    user_id = user.get("user_id")
    if not isinstance(user_id, str) or not user_id:
        raise HTTPException(status_code=401, detail="Invalid authenticated user")
    return user_id
