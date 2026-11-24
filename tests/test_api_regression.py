import uuid
import pytest
from httpx import AsyncClient, ASGITransport
from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.main import app
from app.core.db import async_session_maker
from app.core.tokens import create_customer_token, create_admin_token
from app.models.user import User, Role
from app.models.address import Address


@pytest.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac


@pytest.mark.asyncio
async def test_categories_api(client: AsyncClient):
    """Verify GET /categories works with real database."""
    res = await client.get("/categories")
    assert res.status_code == 200
    data = res.json()
    assert isinstance(data, list)
    if len(data) > 0:
        cat = data[0]
        assert "id" in cat
        assert "name" in cat
        assert "slug" in cat


@pytest.mark.asyncio
async def test_products_api(client: AsyncClient):
    """Verify GET /products and GET /products/{slug} work with real database."""
    res = await client.get("/products")
    assert res.status_code == 200
    data = res.json()
    assert "items" in data
    assert "total" in data
    assert isinstance(data["items"], list)

    if len(data["items"]) > 0:
        first_product = data["items"][0]
        slug = first_product["slug"]
        detail_res = await client.get(f"/products/{slug}")
        assert detail_res.status_code == 200
        detail = detail_res.json()
        assert detail["slug"] == slug
        assert "price_paise" in detail
        assert "cost_price_paise" in detail
        assert "gst_rate_percent" in detail


@pytest.mark.asyncio
async def test_payment_methods_api(client: AsyncClient):
    """Verify GET /payments/methods returns seeded payment methods."""
    res = await client.get("/payments/methods")
    assert res.status_code == 200
    methods = res.json()
    assert isinstance(methods, list)
    codes = [m["code"] for m in methods]
    assert "cod" in codes


@pytest.mark.asyncio
async def test_pincodes_api(client: AsyncClient):
    """Verify GET /delivery/check works."""
    res = await client.get("/delivery/check?pincode=500001")
    # Pincode may or may not be seeded, but API must return valid status (200 or 404/serviceable=False)
    assert res.status_code in (200, 404)


@pytest.mark.asyncio
async def test_addresses_api_flow(client: AsyncClient):
    """Verify addresses CRUD flow for customer."""
    test_user_id = str(uuid.uuid4())
    test_email = f"addr-test-{uuid.uuid4().hex[:6]}@example.com"

    async with async_session_maker() as session:
        user = User(
            id=uuid.UUID(test_user_id),
            role=Role.customer,
            email=test_email,
            is_active=True,
        )
        session.add(user)
        await session.commit()

    token = create_customer_token(test_user_id)
    headers = {"Authorization": f"Bearer {token}"}

    try:
        # List addresses -> initially empty
        res = await client.get("/addresses", headers=headers)
        assert res.status_code == 200
        assert res.json() == []

        # Create address
        payload = {
            "full_name": "Test User",
            "phone": "9876543210",
            "line1": "123 Main Street",
            "city": "Hyderabad",
            "state": "Telangana",
            "pincode": "500001",
            "is_default": True,
        }
        create_res = await client.post("/addresses", json=payload, headers=headers)
        assert create_res.status_code == 201
        addr = create_res.json()
        assert addr["full_name"] == "Test User"
        assert addr["is_default"] is True
        addr_id = addr["id"]

        # Get address list -> should contain 1
        list_res = await client.get("/addresses", headers=headers)
        assert list_res.status_code == 200
        assert len(list_res.json()) == 1

        # Delete address
        del_res = await client.delete(f"/addresses/{addr_id}", headers=headers)
        assert del_res.status_code == 204

        # Verify address deleted
        after_del = await client.get("/addresses", headers=headers)
        assert after_del.status_code == 200
        assert len(after_del.json()) == 0
    finally:
        async with async_session_maker() as session:
            await session.execute(delete(Address).where(Address.user_id == uuid.UUID(test_user_id)))
            await session.execute(delete(User).where(User.id == uuid.UUID(test_user_id)))
            await session.commit()


@pytest.mark.asyncio
async def test_cart_validate_api(client: AsyncClient):
    """Verify POST /cart/validate endpoint."""
    res = await client.post("/cart/validate", json={"items": []})
    assert res.status_code == 200
    data = res.json()
    assert data["items"] == []
    assert data["subtotal_paise"] == 0
