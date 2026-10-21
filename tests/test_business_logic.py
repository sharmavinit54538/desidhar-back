import pytest
import uuid
from decimal import Decimal
from unittest.mock import MagicMock, AsyncMock

from app.models.user import User, UserRole, UserStatus
from app.models.catalog import Product, ProductStatus
from app.models.order import OrderItem
from app.core.dependencies import RoleChecker, PermissionChecker
from app.core.exceptions import ForbiddenException, BadRequestException
from app.services.catalog_service import CatalogService


@pytest.mark.asyncio
async def test_role_checker_passes_for_allowed_role():
    checker = RoleChecker([UserRole.SUPER_ADMIN, UserRole.STORE_MANAGER])
    admin_user = User(
        id=uuid.uuid4(),
        email="admin@test.com",
        role=UserRole.SUPER_ADMIN,
        status=UserStatus.ACTIVE,
    )
    result = await checker(admin_user)
    assert result.id == admin_user.id


@pytest.mark.asyncio
async def test_role_checker_fails_for_disallowed_role():
    checker = RoleChecker([UserRole.SUPER_ADMIN])
    customer_user = User(
        id=uuid.uuid4(),
        email="cust@test.com",
        role=UserRole.CUSTOMER,
        status=UserStatus.ACTIVE,
    )
    with pytest.raises(ForbiddenException) as exc_info:
        await checker(customer_user)
    assert exc_info.value.error_code == "INSUFFICIENT_ROLE"


@pytest.mark.asyncio
async def test_permission_checker_super_admin_bypass():
    checker = PermissionChecker(["order:refund", "inventory:update"])
    admin_user = User(
        id=uuid.uuid4(),
        email="admin@test.com",
        role=UserRole.SUPER_ADMIN,
        permissions=[],  # Empty list, but SUPER_ADMIN auto-passes
        status=UserStatus.ACTIVE,
    )
    result = await checker(admin_user)
    assert result.role == UserRole.SUPER_ADMIN


@pytest.mark.asyncio
async def test_permission_checker_staff_evaluation():
    checker = PermissionChecker(["product:write"])
    staff_with_perm = User(
        id=uuid.uuid4(),
        email="staff@test.com",
        role=UserRole.STORE_MANAGER,
        permissions=["product:write", "order:read"],
        status=UserStatus.ACTIVE,
    )
    staff_without_perm = User(
        id=uuid.uuid4(),
        email="staff2@test.com",
        role=UserRole.SUPPORT_STAFF,
        permissions=["order:read"],
        status=UserStatus.ACTIVE,
    )

    # Has permission -> succeeds
    res = await checker(staff_with_perm)
    assert res.email == "staff@test.com"

    # Missing permission -> raises 403
    with pytest.raises(ForbiddenException) as exc_info:
        await checker(staff_without_perm)
    assert exc_info.value.error_code == "INSUFFICIENT_PERMISSIONS"


@pytest.mark.asyncio
async def test_permanent_delete_protects_ordered_products():
    """
    Guarantees hard-deleting a product linked to existing order items raises BadRequestException.
    """
    mock_db = AsyncMock()
    product_id = uuid.uuid4()
    dummy_product = Product(
        id=product_id,
        name="Test Kurta",
        sku="TEST-SKU-1",
        base_price=Decimal("1999.00"),
        stock=10,
        status=ProductStatus.ACTIVE,
    )

    # Mock get_product_by_id
    mock_result_product = MagicMock()
    mock_result_product.scalar_one_or_none.return_value = dummy_product

    # Mock count query returning 5 historical order items
    mock_result_count = MagicMock()
    mock_result_count.scalar.return_value = 5

    mock_db.execute.side_effect = [mock_result_product, mock_result_count]

    with pytest.raises(BadRequestException) as exc_info:
        await CatalogService.permanent_delete_product(mock_db, product_id)

    assert exc_info.value.error_code == "PRODUCT_LINKED_TO_ORDERS"
    assert "historical order items" in exc_info.value.message
