from fastapi import APIRouter, Depends, HTTPException, Body, UploadFile, File, status
from sqlalchemy.ext.asyncio import AsyncSession
from app.api.deps import get_db, require_admin
from app.models.user import User
from app.schemas.pincode_bulk import BulkUpsertResult
from app.services.pincode_import_service import process_bulk_upsert, process_csv_import

router = APIRouter(prefix="/admin/pincodes", tags=["admin-pincodes"])


@router.post("/bulk", response_model=BulkUpsertResult)
async def bulk_upsert(
    items: list[dict] = Body(...),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_admin),
):
    if len(items) > 500:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Maximum 500 items allowed in bulk upsert")
    return await process_bulk_upsert(db, items)


@router.post("/import", response_model=BulkUpsertResult)
async def import_csv(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_admin),
):
    content = await file.read()
    return await process_csv_import(db, content)

