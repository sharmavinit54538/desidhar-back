"""PostgreSQL-backed regression coverage for real order snapshot persistence.

The test uses existing, deliverable catalog/customer records and rolls back the
order and cart changes so it does not leave fixture orders or consume inventory.
"""
import uuid

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select

from app.models.address import Address
from app.models.cart import Cart
from app.models.cart_item import CartItem
from app.models.delivery_mode import DeliveryMode
from app.models.order import PaymentMethod
from app.models.pincode import Pincode
from app.models.product import Product
from app.models.user import Role, User
from app.api.deps import get_db
from app.core.tokens import create_admin_token, create_customer_token
from app.main import app
from app.services.order_service import place_order

@pytest.mark.asyncio
async def test_order_creation_persists_real_snapshots_and_rolls_back(db_session):
    session = db_session
    candidates = (await session.execute(
            select(User, Address, Product, Cart)
            .join(Address, Address.user_id == User.id)
            .join(Pincode, Pincode.pincode == Address.pincode)
            .join(Product, Product.is_active.is_(True))
            .outerjoin(Cart, Cart.user_id == User.id)
            .where(
                User.role == Role.customer,
                Address.deleted_at.is_(None),
                Pincode.is_serviceable.is_(True),
                Product.stock_qty > 0,
                Product.delivery_mode == DeliveryMode.all,
                Product.price_paise >= Pincode.min_order_paise,
            )
            .limit(1)
        )).first()
    if not candidates:
        pytest.skip("Configured PostgreSQL database has no eligible customer/order fixtures")
    user, address, product, cart = candidates
    if cart is None:
        cart = Cart(user_id=user.id)
        session.add(cart)
        await session.flush()
    cart.items.clear()
    cart.items.append(CartItem(product_id=product.id, quantity=1))
    second_product = await session.scalar(
        select(Product).where(
            Product.id != product.id,
            Product.is_active.is_(True), Product.stock_qty > 0,
            Product.delivery_mode == DeliveryMode.all,
        ).limit(1)
    )
    if second_product:
        cart.items.append(CartItem(product_id=second_product.id, quantity=1))
    await session.flush()

    order, error = await place_order(
        session, user, address.id, PaymentMethod.online.value,
        f"integration-{uuid.uuid4()}",
    )
    assert error is None
    assert order is not None
    assert len(order.items) == (2 if second_product else 1)
    snapshot = next(item for item in order.items if item.product_id == product.id)
    assert snapshot.name_snapshot == product.name
    assert snapshot.pack_size_snapshot == product.pack_size
    assert snapshot.unit_price_paise == product.price_paise
    assert snapshot.unit_mrp_paise == product.mrp_paise
    assert snapshot.line_total_paise == product.price_paise
    assert snapshot.sku_snapshot is None  # There is no SKU source in the current catalog model.
    assert snapshot.image_url_snapshot == (product.images[0].url if product.images else None)
    expected_subtotal = product.price_paise + (second_product.price_paise if second_product else 0)
    assert order.subtotal_paise == expected_subtotal
    assert order.total_paise == order.subtotal_paise - order.discount_paise + order.delivery_fee_paise
    assert order.payments[0].amount_paise == order.total_paise
    assert order.history[0].to_status == order.status.value
    assert order.status.value == "payment_pending"

    # db_session is closed without commit by the fixture; teardown rolls this back.


@pytest.mark.asyncio
async def test_post_orders_returns_saved_order_without_schema_error(db_session):
    candidates = (await db_session.execute(
        select(User, Address, Product)
        .join(Address, Address.user_id == User.id)
        .join(Pincode, Pincode.pincode == Address.pincode)
        .join(Product, Product.is_active.is_(True))
        .where(
            User.role == Role.customer,
            Address.deleted_at.is_(None), Pincode.is_serviceable.is_(True),
            Product.stock_qty > 0, Product.delivery_mode == DeliveryMode.all,
            Product.price_paise >= Pincode.min_order_paise,
        )
        .limit(1)
    )).first()
    if not candidates:
        pytest.skip("Configured PostgreSQL database has no eligible customer/order fixtures")
    user, address, product = candidates
    admin_user = await db_session.scalar(select(User).where(User.role == Role.admin).limit(1))
    if not admin_user:
        pytest.skip("Configured PostgreSQL database has no admin fixture")

    # Reproduce the checkout failure from a cart that already contains the
    # product also sent in the order payload.
    cart = await db_session.scalar(select(Cart).where(Cart.user_id == user.id))
    if cart is None:
        cart = Cart(user_id=user.id)
        db_session.add(cart)
        await db_session.flush()
    existing_item = next((item for item in cart.items if item.product_id == product.id), None)
    if existing_item:
        existing_item.quantity = 1
    else:
        cart.items.append(CartItem(product_id=product.id, quantity=1))
    await db_session.flush()

    async def rollback_session():
        yield db_session

    original = app.dependency_overrides.get(get_db)
    app.dependency_overrides[get_db] = rollback_session
    try:
        checkout_key = f"api-test-{uuid.uuid4()}"
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                "/orders",
                headers={"Authorization": f"Bearer {create_customer_token(str(user.id))}", "Idempotency-Key": checkout_key},
                json={"address_id": str(address.id), "payment_method": "cod",
                      "items": [{"product_id": str(product.id), "quantity": 1}]},
            )
        assert response.status_code == 201, response.text
        payload = response.json()
        assert payload["order"]["items"][0]["name_snapshot"] == product.name
        assert payload["order"]["items"][0]["image_url"] == (product.images[0].url if product.images else None)
        assert payload["order"]["items"][0]["unit_price_paise"] == product.price_paise
        assert payload["order"]["total_paise"] > 0
        assert payload["order"]["status"] == "placed"
        assert "confirmed" in payload["order"]["allowed_actions"]

        order_id = payload["order"]["id"]
        admin_headers = {"Authorization": f"Bearer {create_admin_token(str(admin_user.id))}"}
        expected_version = payload["order"]["version"]
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as workflow_client:
            retry = await workflow_client.post(
                "/orders",
                headers={"Authorization": f"Bearer {create_customer_token(str(user.id))}", "Idempotency-Key": checkout_key},
                json={"address_id": str(address.id), "payment_method": "cod",
                      "items": [{"product_id": str(product.id), "quantity": 1}]},
            )
            assert retry.status_code == 201, retry.text
            assert retry.json()["order"]["id"] == order_id
            remaining_cart_items = await db_session.scalar(
                select(func.count()).select_from(CartItem).where(CartItem.cart_id == cart.id)
            )
            assert remaining_cart_items == 0

            for stage, next_stage in [
                ("confirmed", "packed"),
                ("packed", "shipped"),
                ("shipped", "out_for_delivery"),
                ("out_for_delivery", "delivered"),
                ("delivered", "return_requested"),
            ]:
                changed = await workflow_client.post(
                    f"/admin/orders/{order_id}/status", headers=admin_headers,
                    json={"status": stage, "expected_version": expected_version},
                )
                assert changed.status_code == 200, changed.text
                changed_order = changed.json()
                assert changed_order["status"] == stage
                assert changed_order["version"] == expected_version + 1
                assert next_stage in changed_order["allowed_actions"]
                assert any(item["to_status"] == stage for item in changed_order["history"])
                expected_version = changed_order["version"]
                if stage == "confirmed":
                    stale = await workflow_client.post(
                        f"/admin/orders/{order_id}/status", headers=admin_headers,
                        json={"status": "packed", "expected_version": expected_version - 1},
                    )
                    assert stale.status_code == 409
                    assert "concurrently" in stale.json()["detail"].lower()
                    assert "current='confirmed'" in stale.json()["detail"]
            assert changed_order["payment_status"] == "pending"

            customer_detail = await workflow_client.get(
                f"/orders/{order_id}",
                headers={"Authorization": f"Bearer {create_customer_token(str(user.id))}"},
            )
            assert customer_detail.status_code == 200, customer_detail.text
            assert customer_detail.json()["status"] == "delivered"
            assert customer_detail.json()["payment_status"] == "pending"

            invalid = await workflow_client.post(
                f"/admin/orders/{order_id}/status", headers=admin_headers,
                json={"status": "confirmed", "expected_version": expected_version},
            )
            assert invalid.status_code == 409
            assert "current='delivered'" in invalid.json()["detail"]
            assert "requested='confirmed'" in invalid.json()["detail"]
            assert "permitted next statuses: return_requested" in invalid.json()["detail"].lower()
    finally:
        if original is None:
            app.dependency_overrides.pop(get_db, None)
        else:
            app.dependency_overrides[get_db] = original
