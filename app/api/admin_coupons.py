import uuid
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from app.api.deps import get_db, require_admin
from app.models.user import User
from app.schemas.coupon import CouponCreate, CouponUpdate, CouponOut
from app.services.coupon_service import (
    list_coupons, get_coupon_by_code, create_coupon, update_coupon, delete_coupon,
)
from sqlalchemy import select
from app.models.coupon import Coupon

router = APIRouter(prefix="/admin/coupons", tags=["admin-coupons"])


@router.post("", response_model=CouponOut, status_code=status.HTTP_201_CREATED)
async def create(data: CouponCreate, db: AsyncSession = Depends(get_db), _: User = Depends(require_admin)):
    if await get_coupon_by_code(db, data.code):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Coupon code already exists")
    return await create_coupon(db, data.model_dump())


@router.get("", response_model=list[CouponOut])
async def list_all(db: AsyncSession = Depends(get_db), _: User = Depends(require_admin)):
    return await list_coupons(db)


@router.get("/{coupon_id}", response_model=CouponOut)
async def get_one(coupon_id: uuid.UUID, db: AsyncSession = Depends(get_db), _: User = Depends(require_admin)):
    c = (await db.execute(select(Coupon).where(Coupon.id == coupon_id))).scalar_one_or_none()
    if not c:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Coupon not found")
    return c


@router.patch("/{coupon_id}", response_model=CouponOut)
async def patch(coupon_id: uuid.UUID, data: CouponUpdate, db: AsyncSession = Depends(get_db), _: User = Depends(require_admin)):
    c = (await db.execute(select(Coupon).where(Coupon.id == coupon_id))).scalar_one_or_none()
    if not c:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Coupon not found")
    up = data.model_dump(exclude_unset=True)
    if "code" in up and up["code"] != c.code:
        if await get_coupon_by_code(db, up["code"]):
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Coupon code already exists")
    return await update_coupon(db, c, up)


@router.delete("/{coupon_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove(coupon_id: uuid.UUID, db: AsyncSession = Depends(get_db), _: User = Depends(require_admin)):
    c = (await db.execute(select(Coupon).where(Coupon.id == coupon_id))).scalar_one_or_none()
    if not c:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Coupon not found")
    await delete_coupon(db, c)

