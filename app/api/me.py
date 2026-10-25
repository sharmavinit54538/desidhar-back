from fastapi import APIRouter, Depends, HTTPException, status
from app.api.deps import get_current_user
from app.api.roles import require_role
from app.schemas.auth import UserResponse
from app.models.user import User, Role

router = APIRouter(tags=["me"])


@router.get("/me", response_model=UserResponse)
async def get_me(current_user: User = Depends(get_current_user)):
    return UserResponse(
        id=str(current_user.id),
        role=current_user.role.value,
        email=current_user.email,
        username=current_user.username,
        is_active=current_user.is_active,
        created_at=current_user.created_at.isoformat(),
    )


@router.get("/admin/ping")
@require_role(Role.admin)
async def admin_ping(current_user: User = Depends(get_current_user)):
    return {"message": "pong", "admin": current_user.username}