import uuid
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from app.api.deps import get_db, get_current_user
from app.models.user import User
from app.schemas.address import AddressCreate, AddressUpdate, AddressOut
from app.services.address_service import (
    list_addresses, get_address, create_address, update_address, delete_address, set_default_address,
)

router = APIRouter(prefix="/addresses", tags=["addresses"])


@router.post("", response_model=AddressOut, status_code=status.HTTP_201_CREATED)
async def create(data: AddressCreate, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    addr, err = await create_address(db, user.id, data.model_dump())
    if err:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=err)
    return addr


@router.get("", response_model=list[AddressOut])
async def list_all(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return await list_addresses(db, user.id)


@router.patch("/{address_id}", response_model=AddressOut)
async def patch(address_id: uuid.UUID, data: AddressUpdate, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    addr = await get_address(db, user.id, address_id)
    if not addr:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Address not found")
    return await update_address(db, addr, data.model_dump(exclude_unset=True))


@router.delete("/{address_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove(address_id: uuid.UUID, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    addr = await get_address(db, user.id, address_id)
    if not addr:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Address not found")
    await delete_address(db, addr)


@router.post("/{address_id}/default", response_model=AddressOut)
async def make_default(address_id: uuid.UUID, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    addr = await get_address(db, user.id, address_id)
    if not addr:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Address not found")
    return await set_default_address(db, addr)

