from fastapi import APIRouter, HTTPException, Depends
from models.schemas import UserPrefs
from services.supabase_client import get_supabase
from dependencies import get_user_id

router = APIRouter(prefix="/api/prefs", tags=["preferences"])


@router.get("", response_model=UserPrefs)
async def get_prefs(  # type: ignore[no-untyped-def]
    supabase=Depends(get_supabase),
    user_id: str = Depends(get_user_id),
) -> UserPrefs:
    try:
        response = await supabase.table("user_prefs").select("*").eq("user_id", user_id).single().execute()
        if response.data:
            return response.data  # type: ignore[no-any-return]
        return UserPrefs()
    except Exception:
        return UserPrefs()


@router.post("", response_model=UserPrefs)
async def update_prefs(  # type: ignore[no-untyped-def]
    prefs: UserPrefs,
    supabase=Depends(get_supabase),
    user_id: str = Depends(get_user_id),
) -> UserPrefs:
    try:
        await supabase.table("user_prefs").upsert({
            "user_id": user_id,
            "preferred_model": prefs.preferred_model,
            "interests": prefs.interests,
        }).execute()
        return prefs
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
