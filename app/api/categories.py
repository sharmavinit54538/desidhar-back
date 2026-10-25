from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from app.api.deps import get_db
from app.schemas.category import CategoryOut
from app.services.category_service import list_active_categories

router = APIRouter(prefix="/categories", tags=["categories"])


@router.get("", response_model=list[CategoryOut])
async def get_categories(db: AsyncSession = Depends(get_db)):
    return await list_active_categories(db)

