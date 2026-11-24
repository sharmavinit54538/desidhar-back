from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from app.api.deps import get_current_user, get_db
from app.api.roles import require_role
from app.schemas.auth import UserResponse, UserUpdate
from app.models.user import User, Role

router = APIRouter(tags=["me"])


def profile_response(current_user: User) -> UserResponse:
    return UserResponse(
        id=str(current_user.id),
        role=current_user.role.value,
        email=current_user.email,
        full_name=current_user.full_name,
        phone=current_user.phone,
        username=current_user.username,
        is_active=current_user.is_active,
        created_at=current_user.created_at.isoformat(),
    )


@router.get("/me", response_model=UserResponse)
async def get_me(current_user: User = Depends(get_current_user)):
    return profile_response(current_user)


@router.patch("/me", response_model=UserResponse)
async def update_me(
    data: UserUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(current_user, field, value)
    await db.commit()
    await db.refresh(current_user)
    return profile_response(current_user)


@router.get("/admin/ping")
@require_role(Role.admin)
async def admin_ping(current_user: User = Depends(get_current_user)):
    return {"message": "pong", "admin": current_user.username}
