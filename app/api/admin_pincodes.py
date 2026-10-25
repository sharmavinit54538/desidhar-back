import uuid
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
from app.api.deps import get_db, require_admin
from app.models.user import User
from app.schemas.pincode import (
    PincodeCreate, PincodeUpdate, PincodeServiceableUpdate, PincodeOut, PincodeListOut,
)
from app.services.pincode_service import (
    get_pincode_by_id, get_pincode_by_code, list_pincodes, create_pincode,
    update_pincode, delete_pincode,
)

router = APIRouter(prefix="/admin/pincodes", tags=["admin-pincodes"])


@router.post("", response_model=PincodeOut, status_code=status.HTTP_201_CREATED)
async def create(data: PincodeCreate, db: AsyncSession = Depends(get_db), _: User = Depends(require_admin)):
    if await get_pincode_by_code(db, data.pincode):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Pincode already exists")
    return await create_pincode(db, data.model_dump())


@router.get("", response_model=PincodeListOut)
async def list_all(
    q: str | None = None,
    city: str | None = None,
    state: str | None = None,
    is_serviceable: bool | None = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_admin),
):
    items, total = await list_pincodes(db, q, city, state, is_serviceable, page, page_size)
    return PincodeListOut(items=items, total=total, page=page, page_size=page_size)


@router.get("/{pincode_id}", response_model=PincodeOut)
async def get_one(pincode_id: uuid.UUID, db: AsyncSession = Depends(get_db), _: User = Depends(require_admin)):
    p = await get_pincode_by_id(db, pincode_id)
    if not p:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Pincode not found")
    return p


@router.patch("/{pincode_id}", response_model=PincodeOut)
async def patch(pincode_id: uuid.UUID, data: PincodeUpdate, db: AsyncSession = Depends(get_db), _: User = Depends(require_admin)):
    p = await get_pincode_by_id(db, pincode_id)
    if not p:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Pincode not found")
    up_data = data.model_dump(exclude_unset=True)
    if "pincode" in up_data and up_data["pincode"] != p.pincode:
        if await get_pincode_by_code(db, up_data["pincode"]):
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Pincode already exists")
    return await update_pincode(db, p, up_data)


@router.delete("/{pincode_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove(pincode_id: uuid.UUID, db: AsyncSession = Depends(get_db), _: User = Depends(require_admin)):
    p = await get_pincode_by_id(db, pincode_id)
    if not p:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Pincode not found")
    await delete_pincode(db, p)


@router.patch("/{pincode_id}/serviceable", response_model=PincodeOut)
async def toggle_serviceable(
    pincode_id: uuid.UUID, data: PincodeServiceableUpdate, db: AsyncSession = Depends(get_db), _: User = Depends(require_admin),
):
    p = await get_pincode_by_id(db, pincode_id)
    if not p:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Pincode not found")
    return await update_pincode(db, p, {"is_serviceable": data.is_serviceable})

