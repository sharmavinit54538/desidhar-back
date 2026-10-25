import uuid
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from app.api.deps import get_db, require_admin
from app.models.user import User
from app.schemas.category import CategoryCreate, CategoryUpdate, CategoryOut
from app.services.category_service import (
    list_all_categories, get_category_by_id, create_category, update_category, category_has_products,
)

router = APIRouter(prefix="/admin/categories", tags=["admin-categories"])


@router.post("", response_model=CategoryOut, status_code=status.HTTP_201_CREATED)
async def create(data: CategoryCreate, db: AsyncSession = Depends(get_db), _: User = Depends(require_admin)):
    cat = await create_category(db, data.name, data.sort_order, data.is_active)
    return cat


@router.get("", response_model=list[CategoryOut])
async def list_cats(db: AsyncSession = Depends(get_db), _: User = Depends(require_admin)):
    return await list_all_categories(db)


@router.patch("/{category_id}", response_model=CategoryOut)
async def patch(category_id: uuid.UUID, data: CategoryUpdate, db: AsyncSession = Depends(get_db), _: User = Depends(require_admin)):
    cat = await get_category_by_id(db, category_id)
    if not cat:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Category not found")
    updated = await update_category(db, cat, data.model_dump(exclude_unset=True))
    return updated


@router.delete("/{category_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete(category_id: uuid.UUID, db: AsyncSession = Depends(get_db), _: User = Depends(require_admin)):
    cat = await get_category_by_id(db, category_id)
    if not cat:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Category not found")
    if await category_has_products(db, category_id):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Category has products and cannot be deleted")
    await db.delete(cat)

