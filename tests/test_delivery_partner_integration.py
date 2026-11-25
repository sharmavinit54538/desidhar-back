"""PostgreSQL-backed role isolation and partner assignment workflow checks."""
import uuid

import pytest
from httpx import AsyncClient, ASGITransport
from sqlalchemy import select

from app.api.deps import get_db
from app.core.tokens import create_admin_token, create_customer_token
from app.main import app
from app.models.address import Address
from app.models.cart import Cart
from app.models.cart_item import CartItem
from app.models.delivery_mode import DeliveryMode
from app.models.order import Order
from app.models.pincode import Pincode
from app.models.product import Product
from app.models.user import Role, User
from app.services.order_service import place_order


async def _client_for_session(db_session):
    async def rollback_session():
        yield db_session
    previous = app.dependency_overrides.get(get_db)
    app.dependency_overrides[get_db] = rollback_session
    client = AsyncClient(transport=ASGITransport(app=app), base_url="http://test")
    return client, previous


@pytest.mark.asyncio
async def test_admin_partner_cod_otp_and_settlement_workflow(db_session, monkeypatch):
    admin = await db_session.scalar(select(User).where(User.role == Role.admin).limit(1))
    candidate = (await db_session.execute(
        select(User, Address, Pincode, Product)
        .join(Address, Address.user_id == User.id)
        .join(Pincode, Pincode.pincode == Address.pincode)
        .join(Product, Product.is_active.is_(True))
        .where(User.role == Role.customer, Address.deleted_at.is_(None), Pincode.is_serviceable.is_(True),
               Product.stock_qty > 0, Product.delivery_mode == DeliveryMode.all,
               Product.price_paise >= Pincode.min_order_paise)
        .limit(1)
    )).first()
    if not admin or not candidate:
        pytest.skip("Configured PostgreSQL database has no admin and deliverable customer fixtures")
    customer, address, _, product = candidate
    partner_username = f"dp-{uuid.uuid4().hex[:10]}"
    partner_password = f"Strong-Partner-{uuid.uuid4().hex[:8]}"
    cart = await db_session.scalar(select(Cart).where(Cart.user_id == customer.id))
    if cart is None:
        cart = Cart(user_id=customer.id)
        db_session.add(cart)
    cart.items.clear()
    cart.items.append(CartItem(product_id=product.id, quantity=1))
    await db_session.flush()
    order, error = await place_order(db_session, customer, address.id, "cod", f"dp-order-{uuid.uuid4()}")
    assert error is None and order
    admin_headers = {"Authorization": f"Bearer {create_admin_token(str(admin.id))}"}
    client, previous = await _client_for_session(db_session)
    try:
        created = await client.post("/admin/delivery/partners", headers=admin_headers, json={
            "username": partner_username, "password": partner_password, "full_name": "Delivery Test",
            "phone": "9876543210", "employee_id": f"TEST-{uuid.uuid4().hex[:8]}",
            "service_pincodes": [address.pincode], "max_active_deliveries": 2,
        })
        assert created.status_code == 201, created.text
        partner_id = created.json()["user_id"]
        assert created.json()["availability"] == "offline"

        login = await client.post("/delivery/auth/login", json={"username": partner_username, "password": partner_password})
        assert login.status_code == 200, login.text
        partner_headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
        assert (await client.get("/delivery/profile", headers=partner_headers)).status_code == 200
        assert (await client.get("/admin/delivery/partners", headers=partner_headers)).status_code == 403
        assert (await client.get("/delivery/profile", headers={"Authorization": f"Bearer {create_customer_token(str(customer.id))}"})).status_code == 403

        available = await client.patch("/delivery/availability?availability=available", headers=partner_headers)
        assert available.status_code == 200, available.text
        order_version = order.version
        for status_name in ("confirmed", "packed"):
            changed = await client.post(f"/admin/orders/{order.id}/status", headers=admin_headers,
                json={"status": status_name, "expected_version": order_version})
            assert changed.status_code == 200, changed.text
            order_version = changed.json()["version"]

        assigned = await client.post(f"/admin/delivery/orders/{order.id}/assign", headers=admin_headers,
            json={"partner_id": partner_id})
        assert assigned.status_code == 201, assigned.text
        assert assigned.json()["status"] == "assigned"
        second = await client.post(f"/admin/delivery/orders/{order.id}/assign", headers=admin_headers,
            json={"partner_id": partner_id})
        assert second.status_code == 409

        partner_orders = await client.get("/delivery/orders", headers=partner_headers)
        assert partner_orders.status_code == 200, partner_orders.text
        delivery_order = next(item for item in partner_orders.json() if item["id"] == str(order.id))
        accept = await client.post(f"/delivery/orders/{order.id}/accept", headers=partner_headers,
            json={"expected_version": delivery_order["assignment"]["version"]})
        assert accept.status_code == 200, accept.text
        pickup = await client.post(f"/delivery/orders/{order.id}/pickup", headers=partner_headers,
            json={"expected_version": accept.json()["version"]})
        assert pickup.status_code == 200, pickup.text
        assert pickup.json()["status"] == "picked_up"
        start = await client.post(f"/delivery/orders/{order.id}/start", headers=partner_headers,
            json={"expected_version": pickup.json()["version"]})
        assert start.status_code == 200, start.text
        assert start.json()["fulfillment_status"] == "out_for_delivery"

        order_detail = await client.get(f"/delivery/orders/{order.id}", headers=partner_headers)
        assert order_detail.status_code == 200, order_detail.text
        detail_payload = order_detail.json()
        collection_key = f"cash-{uuid.uuid4()}"
        collected = await client.post(f"/delivery/orders/{order.id}/collect-payment", headers=partner_headers, json={
            "expected_order_version": detail_payload["version"],
            "expected_assignment_version": detail_payload["assignment"]["version"],
            "idempotency_key": collection_key, "amount_paise": detail_payload["outstanding_amount_paise"],
            "method": "cash", "collected_at": "2026-11-25T10:00:00+00:00",
        })
        assert collected.status_code == 200, collected.text
        assert collected.json()["payment_status"] == "paid"
        duplicate = await client.post(f"/delivery/orders/{order.id}/collect-payment", headers=partner_headers, json={
            "expected_order_version": detail_payload["version"],
            "expected_assignment_version": detail_payload["assignment"]["version"],
            "idempotency_key": collection_key, "amount_paise": detail_payload["outstanding_amount_paise"],
            "method": "cash", "collected_at": "2026-11-25T10:00:00+00:00",
        })
        assert duplicate.status_code == 200, duplicate.text

        sent = {}
        async def capture_delivery_email(email, code, order_number):
            sent.update(email=email, code=code, order_number=order_number)
        monkeypatch.setattr("app.api.delivery_management.send_delivery_otp_email", capture_delivery_email)
        requested = await client.post(f"/delivery/orders/{order.id}/request-otp", headers=partner_headers)
        assert requested.status_code == 202, requested.text
        completed = await client.post(f"/delivery/orders/{order.id}/verify-otp", headers=partner_headers,
            json={"otp": sent["code"]})
        assert completed.status_code == 200, completed.text
        assert completed.json()["order_status"] == "delivered"
        assert completed.json()["payment_status"] == "paid"

        submitted = await client.post("/delivery/cash/settlements", headers=partner_headers,
            json={"note": "Integration test deposit"})
        assert submitted.status_code == 201, submitted.text
        expected_amount = submitted.json()["expected_amount_paise"]
        review_list = await client.get("/admin/delivery/settlements", headers=admin_headers)
        assert review_list.status_code == 200, review_list.text
        settlement_id = submitted.json()["id"]
        review = await client.post(f"/admin/delivery/settlements/{settlement_id}/reconcile", headers=admin_headers,
            json={"verified_amount_paise": expected_amount, "deposit_reference": f"test-{uuid.uuid4().hex[:8]}"})
        assert review.status_code == 200, review.text
        assert review.json()["status"] == "approved"
        cash_summary = await client.get("/delivery/cash/summary", headers=partner_headers)
        assert cash_summary.status_code == 200, cash_summary.text
        assert cash_summary.json()["deposited_paise"] == expected_amount
    finally:
        await client.aclose()
        if previous is None:
            app.dependency_overrides.pop(get_db, None)
        else:
            app.dependency_overrides[get_db] = previous
