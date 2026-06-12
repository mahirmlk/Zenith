from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
import jwt
from jwt.exceptions import DecodeError as JWTError
from config import get_settings

router = APIRouter(prefix="/api/auth", tags=["auth"])


class TokenRequest(BaseModel):
    token: str


class TokenResponse(BaseModel):
    valid: bool
    user_id: str | None = None


def verify_supabase_token(token: str) -> dict:  # type: ignore[type-arg]
    settings = get_settings()
    if not settings.supabase_jwt_secret:
        raise HTTPException(status_code=500, detail="JWT secret not configured")
    try:
        payload = jwt.decode(token, settings.supabase_jwt_secret, algorithms=["HS256"])
        return payload
    except JWTError as e:
        raise HTTPException(status_code=401, detail=f"Invalid token: {e}")


@router.post("/token", response_model=TokenResponse)
async def validate_token(req: TokenRequest) -> TokenResponse:
    try:
        payload = verify_supabase_token(req.token)
        user_id = payload.get("sub")
        return TokenResponse(valid=True, user_id=user_id)
    except HTTPException:
        return TokenResponse(valid=False)
