from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from jwt.exceptions import InvalidTokenError
from services.jwt_validator import decode_supabase_token
from config import get_settings

router = APIRouter(prefix="/api/auth", tags=["auth"])


class TokenRequest(BaseModel):
    token: str


class TokenResponse(BaseModel):
    valid: bool
    user_id: str | None = None


async def verify_supabase_token(token: str) -> dict:  # type: ignore[type-arg]
    settings = get_settings()
    if not settings.supabase_url and not settings.supabase_jwt_secret:
        raise HTTPException(status_code=500, detail="JWT validation not configured")
    try:
        return await decode_supabase_token(token)
    except InvalidTokenError as e:
        raise HTTPException(status_code=401, detail=f"Invalid token: {e}")


@router.post("/token", response_model=TokenResponse)
async def validate_token(req: TokenRequest) -> TokenResponse:
    try:
        payload = await verify_supabase_token(req.token)
        user_id = payload.get("sub")
        return TokenResponse(valid=True, user_id=user_id)
    except HTTPException:
        return TokenResponse(valid=False)