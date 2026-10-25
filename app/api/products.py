from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
from app.api.deps import get_db
from app.schemas.product import ProductOut, ProductListOut
from app.services.product_service import list_products, get_product_by_slug

router = APIRouter(prefix="/products", tags=["products"])


@router.get("", response_model=ProductListOut)
async def get_products(
    q: str | None = None,
    category: str | None = None,
    min_price: int | None = Query(default=None, ge=0),
    max_price: int | None = Query(default=None, ge=0),
    in_stock: bool | None = None,
    sort: str = Query(default="newest", pattern="^(newest|price_asc|price_desc|name)$"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
):
    items, total = await list_products(
        db, q=q, category_slug=category, min_price=min_price, max_price=max_price,
        in_stock=in_stock, sort=sort, page=page, page_size=page_size, active_only=True,
    )
    return ProductListOut(items=items, total=total, page=page, page_size=page_size)


@router.get("/{slug}", response_model=ProductOut)
async def get_product(slug: str, db: AsyncSession = Depends(get_db)):
    product = await get_product_by_slug(db, slug, active_only=True)
    if not product:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")
    return product

