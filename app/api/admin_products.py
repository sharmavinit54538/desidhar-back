import uuid
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
from app.api.deps import get_db, require_admin
from app.models.user import User
from app.schemas.product import ProductCreate, ProductUpdate, ProductOut, ProductListOut
from app.services.product_service import (
    create_product, update_product, get_product_by_id, list_products,
)
from app.services.category_service import get_category_by_id

router = APIRouter(prefix="/admin/products", tags=["admin-products"])


@router.post("", response_model=ProductOut, status_code=status.HTTP_201_CREATED)
async def create(data: ProductCreate, db: AsyncSession = Depends(get_db), _: User = Depends(require_admin)):
    cat = await get_category_by_id(db, data.category_id)
    if not cat:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Category not found")
    product_data = data.model_dump()
    product_data["images"] = [img.model_dump() for img in data.images]
    product = await create_product(db, product_data)
    return product


@router.get("", response_model=ProductListOut)
async def list_all(
    q: str | None = None,
    category: str | None = None,
    min_price: int | None = Query(default=None, ge=0),
    max_price: int | None = Query(default=None, ge=0),
    in_stock: bool | None = None,
    sort: str = Query(default="newest", pattern="^(newest|price_asc|price_desc|name)$"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_admin),
):
    items, total, _ = await list_products(
        db, q=q, category_slug=category, min_price=min_price, max_price=max_price,
        in_stock=in_stock, sort=sort, page=page, page_size=page_size, active_only=False,
    )
    return ProductListOut(items=items, total=total, page=page, page_size=page_size)


@router.get("/{product_id}", response_model=ProductOut)
async def get_one(product_id: uuid.UUID, db: AsyncSession = Depends(get_db), _: User = Depends(require_admin)):
    product = await get_product_by_id(db, product_id)
    if not product:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")
    return product


@router.patch("/{product_id}", response_model=ProductOut)
async def patch(product_id: uuid.UUID, data: ProductUpdate, db: AsyncSession = Depends(get_db), _: User = Depends(require_admin)):
    product = await get_product_by_id(db, product_id)
    if not product:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")
    if data.category_id is not None:
        cat = await get_category_by_id(db, data.category_id)
        if not cat:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Category not found")
    update_data = data.model_dump(exclude_unset=True)
    if "images" in update_data and update_data["images"] is not None:
        update_data["images"] = [img.model_dump() for img in data.images]
    # Validate price <= mrp after merge
    new_price = update_data.get("price_paise", product.price_paise)
    new_mrp = update_data.get("mrp_paise", product.mrp_paise)
    if new_price > new_mrp:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="price_paise must not exceed mrp_paise")
    product = await update_product(db, product, update_data)
    return product


@router.delete("/{product_id}", status_code=status.HTTP_204_NO_CONTENT)
async def soft_delete(product_id: uuid.UUID, db: AsyncSession = Depends(get_db), _: User = Depends(require_admin)):
    product = await get_product_by_id(db, product_id)
    if not product:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")
    product.is_active = False
    await db.flush()


@router.post("/{product_id}/restore", response_model=ProductOut)
async def restore(product_id: uuid.UUID, db: AsyncSession = Depends(get_db), _: User = Depends(require_admin)):
    product = await get_product_by_id(db, product_id)
    if not product:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")
    product.is_active = True
    await db.flush()
    await db.refresh(product)
    return product

