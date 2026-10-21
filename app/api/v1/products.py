import uuid
from decimal import Decimal
from typing import List, Optional
from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.dependencies import (
    get_current_user,
    RoleChecker,
    PermissionChecker,
)
from app.models.user import User, UserRole
from app.schemas.catalog import (
    CategoryCreate,
    CategoryResponse,
    ProductCreate,
    ProductUpdate,
    ProductResponse,
)
from app.schemas.common import PaginatedResponse
from app.services.catalog_service import catalog_service

router = APIRouter(tags=["Catalog & Safe Deletion"])


# ------------------ PUBLIC CATALOG ENDPOINTS ------------------

@router.get(
    "/products",
    response_model=PaginatedResponse[ProductResponse],
    summary="List active products with filters and pagination",
)
async def list_products(
    search: Optional[str] = Query(None, description="Search term for product name, description, or SKU"),
    category_id: Optional[uuid.UUID] = Query(None, description="Filter by category ID"),
    category_slug: Optional[str] = Query(None, description="Filter by category slug"),
    min_price: Optional[Decimal] = Query(None, ge=0, description="Minimum price filter"),
    max_price: Optional[Decimal] = Query(None, ge=0, description="Maximum price filter"),
    in_stock_only: bool = Query(False, description="Filter in-stock items only"),
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    items, total = await catalog_service.list_public_products(
        db=db,
        search=search,
        category_id=category_id,
        category_slug=category_slug,
        min_price=min_price,
        max_price=max_price,
        in_stock_only=in_stock_only,
        page=page,
        size=size,
    )
    pages = (total + size - 1) // size if total > 0 else 0
    return PaginatedResponse(
        items=[ProductResponse.model_validate(p) for p in items],
        total=total,
        page=page,
        size=size,
        pages=pages,
    )


@router.get(
    "/products/{slug}",
    response_model=ProductResponse,
    summary="Get active product by slug",
)
async def get_product_by_slug(
    slug: str,
    db: AsyncSession = Depends(get_db),
):
    product = await catalog_service.get_product_by_slug(db, slug)
    return ProductResponse.model_validate(product)


@router.get(
    "/categories",
    response_model=List[CategoryResponse],
    summary="List all active product categories",
)
async def list_categories(
    db: AsyncSession = Depends(get_db),
):
    categories = await catalog_service.get_all_categories(db, only_active=True)
    return [CategoryResponse.model_validate(c) for c in categories]


# ------------------ ADMIN CATALOG MANAGEMENT ------------------

@router.post(
    "/admin/categories",
    response_model=CategoryResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[
        Depends(RoleChecker([UserRole.SUPER_ADMIN, UserRole.STORE_MANAGER])),
        Depends(PermissionChecker(["category:write"])),
    ],
    summary="Create category (SUPER_ADMIN or STORE_MANAGER with category:write)",
)
async def create_category(
    data: CategoryCreate,
    db: AsyncSession = Depends(get_db),
):
    category = await catalog_service.create_category(db, data)
    return CategoryResponse.model_validate(category)


@router.post(
    "/admin/products",
    response_model=ProductResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[
        Depends(RoleChecker([UserRole.SUPER_ADMIN, UserRole.STORE_MANAGER])),
        Depends(PermissionChecker(["product:write"])),
    ],
    summary="Create product (SUPER_ADMIN or STORE_MANAGER with product:write)",
)
async def create_product(
    data: ProductCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    product = await catalog_service.create_product(db, data, creator_id=current_user.id)
    return ProductResponse.model_validate(product)


@router.patch(
    "/admin/products/{id}",
    response_model=ProductResponse,
    dependencies=[
        Depends(RoleChecker([UserRole.SUPER_ADMIN, UserRole.STORE_MANAGER])),
        Depends(PermissionChecker(["product:write"])),
    ],
    summary="Update product (SUPER_ADMIN or STORE_MANAGER with product:write)",
)
async def update_product(
    id: uuid.UUID,
    data: ProductUpdate,
    db: AsyncSession = Depends(get_db),
):
    product = await catalog_service.update_product(db, id, data)
    return ProductResponse.model_validate(product)


@router.delete(
    "/admin/products/{id}/archive",
    response_model=ProductResponse,
    dependencies=[
        Depends(RoleChecker([UserRole.SUPER_ADMIN, UserRole.STORE_MANAGER])),
        Depends(PermissionChecker(["product:write"])),
    ],
    summary="Safe soft-delete product (Archive) to preserve order and invoice integrity",
)
async def archive_product(
    id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    product = await catalog_service.archive_product(db, id)
    return ProductResponse.model_validate(product)


@router.delete(
    "/admin/products/{id}/permanent",
    status_code=status.HTTP_200_OK,
    dependencies=[
        Depends(RoleChecker([UserRole.SUPER_ADMIN])),
    ],
    summary="Permanent hard-delete (SUPER_ADMIN only, blocked if linked to past order items)",
)
async def permanent_delete_product(
    id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    await catalog_service.permanent_delete_product(db, id)
    return {"message": "Product permanently deleted from database"}
