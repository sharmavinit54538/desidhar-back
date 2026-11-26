"""End-to-end PostgreSQL integration tests for Delivery Partner Dashboard workflow, atomic COD completion, failure reporting, and tracking sync."""
import uuid

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, select

from app.api.deps import get_db
from app.core.tokens import create_admin_token, create_customer_token
from app.main import app
from app.models.address import Address
from app.models.cart import Cart
from app.models.cart_item import CartItem
from app.models.delivery_finance import CODCollection, DeliveryOTP
from app.models.delivery_management import (
    DeliveryAssignment,
    DeliveryAssignmentHistory,
    DeliveryPartnerProfile,
)
from app.models.delivery_mode import DeliveryMode
from app.models.order import Order, OrderStatus
from app.models.order_item import OrderItem
from app.models.order_lifecycle import InventoryTransaction, OrderAuditLog, OrderNotification
from app.models.order_status_history import OrderStatusHistory
from app.models.payment import Payment, PaymentStatus
from app.models.pincode import Pincode
from app.models.product import Product
from app.models.user import Role, User
from app.services.order_service import place_order
from tests.conftest import db_test_session_maker


async def _client_for_session(db_session):
    async def rollback_session():
        yield db_session

    previous = app.dependency_overrides.get(get_db)
    app.dependency_overrides[get_db] = rollback_session
    client = AsyncClient(transport=ASGITransport(app=app), base_url="http://test")
    return client, previous


async def _ensure_fixtures(db_session):
    admin = await db_session.scalar(select(User).where(User.role == Role.admin).limit(1))
    customer = await db_session.scalar(select(User).where(User.role == Role.customer).limit(1))
    product = await db_session.scalar(
        select(Product)
        .where(
            Product.is_active.is_(True),
            Product.stock_qty >= 5,
            Product.delivery_mode == DeliveryMode.all,
        )
        .limit(1)
    )
    if not admin or not customer or not product:
        pytest.skip("Configured PostgreSQL database lacks admin, customer, or stocked product fixture")

    pin = await db_session.scalar(select(Pincode).where(Pincode.pincode == "303701"))
    if not pin:
        pin = Pincode(
            pincode="303701",
            area_name="Punana",
            city="Jaipur",
            state="Rajasthan",
            is_serviceable=True,
            delivery_fee_paise=0,
            min_order_paise=0,
            cod_available=True,
        )
        db_session.add(pin)
        await db_session.flush()

    addr = await db_session.scalar(
        select(Address).where(
            Address.user_id == customer.id,
            Address.pincode == "303701",
            Address.deleted_at.is_(None),
        ).limit(1)
    )
    if not addr:
        addr = Address(
            user_id=customer.id,
            full_name="Dash Test Customer",
            phone="9876543210",
            line1="42 Market Street",
            city="Jaipur",
            state="Rajasthan",
            pincode="303701",
            is_default=False,
        )
        db_session.add(addr)
        await db_session.flush()

    return admin, customer, addr, product


async def _create_order(db_session, customer: User, address_id: uuid.UUID, product: Product, method: str = "cod") -> Order:
    cart = await db_session.scalar(select(Cart).where(Cart.user_id == customer.id))
    if cart is None:
        cart = Cart(user_id=customer.id)
        db_session.add(cart)
        await db_session.flush()
    cart.items.clear()
    cart.items.append(CartItem(product_id=product.id, quantity=1))
    await db_session.flush()

    order, error, _ = await place_order(
        db_session, customer, address_id, method, f"dash-e2e-{uuid.uuid4()}"
    )
    assert error is None and order is not None
    return order


async def _create_and_login_partner(client: AsyncClient, admin_headers: dict, max_active: int = 2) -> tuple[str, dict]:
    username = f"dashrider-{uuid.uuid4().hex[:8]}"
    password = f"StrongDash-{uuid.uuid4().hex[:8]}"
    create_res = await client.post(
        "/admin/delivery/partners",
        headers=admin_headers,
        json={
            "username": username,
            "password": password,
            "full_name": f"Rider {username}",
            "phone": "9812345678",
            "employee_id": f"DASH-{uuid.uuid4().hex[:6]}",
            "service_area": "Punana 303701",
            "service_pincodes": ["303701"],
            "max_active_deliveries": max_active,
            "availability": "available",
        },
    )
    assert create_res.status_code == 201, create_res.text
    partner_id = create_res.json()["user_id"]

    login_res = await client.post(
        "/delivery/auth/login",
        json={"username": username, "password": password},
    )
    assert login_res.status_code == 200, login_res.text
    headers = {"Authorization": f"Bearer {login_res.json()['access_token']}"}
    return partner_id, headers


async def _confirm_and_pack(client: AsyncClient, admin_headers: dict, order: Order) -> dict:
    c_res = await client.post(
        f"/admin/orders/{order.id}/status",
        headers=admin_headers,
        json={"status": "confirmed", "expected_version": order.version},
    )
    assert c_res.status_code == 200, c_res.text
    p_res = await client.post(
        f"/admin/orders/{order.id}/status",
        headers=admin_headers,
        json={"status": "packed", "expected_version": c_res.json()["version"]},
    )
    assert p_res.status_code == 200, p_res.text
    return p_res.json()


async def _cleanup_committed(
    order_ids: list[uuid.UUID],
    partner_ids: list[uuid.UUID],
    product_id: uuid.UUID,
    original_stock: int,
):
    async with db_test_session_maker() as cleanup:
        if order_ids:
            await cleanup.execute(delete(DeliveryOTP).where(DeliveryOTP.order_id.in_(order_ids)))
            await cleanup.execute(delete(CODCollection).where(CODCollection.order_id.in_(order_ids)))
            await cleanup.execute(delete(DeliveryAssignmentHistory).where(DeliveryAssignmentHistory.order_id.in_(order_ids)))
            await cleanup.execute(delete(DeliveryAssignment).where(DeliveryAssignment.order_id.in_(order_ids)))
            await cleanup.execute(delete(OrderNotification).where(OrderNotification.order_id.in_(order_ids)))
            await cleanup.execute(delete(OrderAuditLog).where(OrderAuditLog.order_id.in_(order_ids)))
            await cleanup.execute(delete(OrderStatusHistory).where(OrderStatusHistory.order_id.in_(order_ids)))
            await cleanup.execute(delete(InventoryTransaction).where(InventoryTransaction.order_id.in_(order_ids)))
            await cleanup.execute(delete(Payment).where(Payment.order_id.in_(order_ids)))
            await cleanup.execute(delete(OrderItem).where(OrderItem.order_id.in_(order_ids)))
            await cleanup.execute(delete(Order).where(Order.id.in_(order_ids)))
        if partner_ids:
            await cleanup.execute(delete(DeliveryPartnerProfile).where(DeliveryPartnerProfile.user_id.in_(partner_ids)))
            await cleanup.execute(delete(User).where(User.id.in_(partner_ids)))
        prod = await cleanup.get(Product, product_id)
        if prod:
            prod.stock_qty = original_stock
        await cleanup.commit()


@pytest.mark.asyncio
async def test_delivery_partner_dashboard_full_cod_workflow_and_atomic_completion(db_session, monkeypatch):
    admin, customer, addr, product = await _ensure_fixtures(db_session)
    product_id = product.id
    original_stock = product.stock_qty
    order_1 = await _create_order(db_session, customer, addr.id, product, method="cod")
    order_2 = await _create_order(db_session, customer, addr.id, product, method="cod")
    created_order_ids = [order_1.id, order_2.id]
    created_partner_ids: list[uuid.UUID] = []

    sent_otps: list[dict] = []

    async def capture_otp(email: str, code: str, order_number: str):
        sent_otps.append({"email": email, "code": code, "order_number": order_number})

    monkeypatch.setattr("app.api.delivery_management.send_delivery_otp_email", capture_otp)

    admin_headers = {"Authorization": f"Bearer {create_admin_token(str(admin.id))}"}
    customer_headers = {"Authorization": f"Bearer {create_customer_token(str(customer.id))}"}

    client, previous = await _client_for_session(db_session)
    try:
        partner_id, partner_headers = await _create_and_login_partner(client, admin_headers, max_active=1)
        created_partner_ids.append(uuid.UUID(partner_id))

        await _confirm_and_pack(client, admin_headers, order_1)
        await _confirm_and_pack(client, admin_headers, order_2)

        assign_res = await client.post(
            f"/admin/delivery/orders/{order_1.id}/assign",
            headers=admin_headers,
            json={"partner_id": partner_id},
        )
        assert assign_res.status_code == 201, assign_res.text

        # Partner dashboard initial counts & active order payload
        dash_1 = await client.get("/delivery/dashboard", headers=partner_headers)
        assert dash_1.status_code == 200
        assert dash_1.json()["counts"]["assigned"] == 1
        assert len(dash_1.json()["active_deliveries"]) == 1

        active_orders = await client.get("/delivery/orders?scope=active", headers=partner_headers)
        assert active_orders.status_code == 200
        assert len(active_orders.json()) == 1
        card = active_orders.json()[0]
        assert card["order_number"] == order_1.order_number
        assert card["delivery_status"] == "assigned"
        assert card["estimated_delivery_date"] is not None
        assert card["outstanding_amount_paise"] == order_1.total_paise
        assert "internal_admin_note" not in card

        # Workflow: assigned -> accepted -> picked_up -> in_progress (out_for_delivery)
        v = card["assignment"]["version"]
        accept_res = await client.post(
            f"/delivery/orders/{order_1.id}/accept",
            headers=partner_headers,
            json={"expected_version": v},
        )
        assert accept_res.status_code == 200
        assert accept_res.json()["status"] == "accepted"

        pickup_res = await client.post(
            f"/delivery/orders/{order_1.id}/pickup",
            headers=partner_headers,
            json={"expected_version": accept_res.json()["version"]},
        )
        assert pickup_res.status_code == 200
        assert pickup_res.json()["status"] == "picked_up"

        start_res = await client.post(
            f"/delivery/orders/{order_1.id}/start",
            headers=partner_headers,
            json={"expected_version": pickup_res.json()["version"]},
        )
        assert start_res.status_code == 200
        assert start_res.json()["status"] == "in_progress"

        dash_in_progress = await client.get("/delivery/dashboard", headers=partner_headers)
        assert dash_in_progress.json()["counts"]["in_progress"] == 1
        assert dash_in_progress.json()["counts"]["assigned"] == 0

        # Detail endpoint returns current versions
        detail_res = await client.get(f"/delivery/orders/{order_1.id}", headers=partner_headers)
        assert detail_res.status_code == 200
        order_ver = detail_res.json()["version"]
        assign_ver = detail_res.json()["assignment"]["version"]

        # Missing OTP must fail validation (422)
        missing_otp_deliver = await client.post(
            f"/delivery/orders/{order_1.id}/deliver",
            headers=partner_headers,
            json={
                "expected_order_version": order_ver,
                "expected_assignment_version": assign_ver,
                "idempotency_key": f"nootp-{uuid.uuid4()}",
                "cash_collected": True,
                "collected_amount_paise": order_1.total_paise,
            },
        )
        assert missing_otp_deliver.status_code == 422

        # Submitting before requesting OTP must fail with 401
        no_requested_otp = await client.post(
            f"/delivery/orders/{order_1.id}/deliver",
            headers=partner_headers,
            json={
                "expected_order_version": order_ver,
                "expected_assignment_version": assign_ver,
                "idempotency_key": f"noreq-{uuid.uuid4()}",
                "otp": "123456",
                "cash_collected": True,
                "collected_amount_paise": order_1.total_paise,
            },
        )
        assert no_requested_otp.status_code == 401

        # Send delivery OTP to customer (works on unpaid COD while out for delivery)
        otp_req = await client.post(f"/delivery/orders/{order_1.id}/request-otp", headers=partner_headers)
        assert otp_req.status_code == 202, otp_req.text
        assert len(sent_otps) == 1
        actual_otp = sent_otps[-1]["code"]
        wrong_otp = "000000" if actual_otp != "000000" else "999999"

        # Wrong customer OTP must return 401 and must NOT record cash or complete delivery
        wrong_otp_deliver = await client.post(
            f"/delivery/orders/{order_1.id}/deliver",
            headers=partner_headers,
            json={
                "expected_order_version": order_ver,
                "expected_assignment_version": assign_ver,
                "idempotency_key": f"wrongotp-{uuid.uuid4()}",
                "otp": wrong_otp,
                "cash_collected": True,
                "collected_amount_paise": order_1.total_paise,
            },
        )
        assert wrong_otp_deliver.status_code == 401
        assert (await db_session.scalar(select(CODCollection.id).where(CODCollection.order_id == order_1.id))) is None

        # Unconfirmed COD cash collection must fail with 422 even with valid OTP shape
        unconfirmed_deliver = await client.post(
            f"/delivery/orders/{order_1.id}/deliver",
            headers=partner_headers,
            json={
                "expected_order_version": order_ver,
                "expected_assignment_version": assign_ver,
                "idempotency_key": f"unconf-{uuid.uuid4()}",
                "otp": actual_otp,
                "cash_collected": False,
            },
        )
        assert unconfirmed_deliver.status_code == 422

        # Wrong COD amount must fail with 422
        wrong_amount_deliver = await client.post(
            f"/delivery/orders/{order_1.id}/deliver",
            headers=partner_headers,
            json={
                "expected_order_version": order_ver,
                "expected_assignment_version": assign_ver,
                "idempotency_key": f"wrong-{uuid.uuid4()}",
                "otp": actual_otp,
                "cash_collected": True,
                "collected_amount_paise": order_1.total_paise - 100,
            },
        )
        assert wrong_amount_deliver.status_code == 422

        # Confirmed COD cash + valid Customer OTP succeeds atomically
        idemp_key = f"deliver-{uuid.uuid4()}"
        deliver_res = await client.post(
            f"/delivery/orders/{order_1.id}/deliver",
            headers=partner_headers,
            json={
                "expected_order_version": order_ver,
                "expected_assignment_version": assign_ver,
                "idempotency_key": idemp_key,
                "otp": actual_otp,
                "cash_collected": True,
                "collected_amount_paise": order_1.total_paise,
                "note": "Delivered at doorstep and COD cash collected",
            },
        )
        assert deliver_res.status_code == 200, deliver_res.text
        d_body = deliver_res.json()
        assert d_body["order_status"] == "delivered"
        assert d_body["payment_status"] == "paid"
        assert d_body["assignment_status"] == "completed"
        assert d_body["delivered_at"] is not None
        assert d_body["collection_id"] is not None
        assert d_body["collected_amount_paise"] == order_1.total_paise

        # Duplicate completion attempt is rejected with 409 (no duplicate CODCollection)
        dup_deliver = await client.post(
            f"/delivery/orders/{order_1.id}/deliver",
            headers=partner_headers,
            json={
                "expected_order_version": order_ver + 1,
                "expected_assignment_version": assign_ver + 1,
                "idempotency_key": f"dup-{uuid.uuid4()}",
                "otp": actual_otp,
                "cash_collected": True,
                "collected_amount_paise": order_1.total_paise,
            },
        )
        assert dup_deliver.status_code == 409

        cod_count_rows = (
            await db_session.scalars(select(CODCollection).where(CODCollection.order_id == order_1.id))
        ).all()
        assert len(cod_count_rows) == 1

        # Partner capacity released -> order_2 sees partner as eligible again
        eligible_after = await client.get(
            f"/admin/delivery/orders/{order_2.id}/eligible-partners",
            headers=admin_headers,
        )
        assert eligible_after.status_code == 200
        matched = [p for p in eligible_after.json() if p["user_id"] == partner_id]
        assert len(matched) == 1
        assert matched[0]["is_eligible"] is True
        assert matched[0]["remaining_capacity"] == 1

        # Dashboard & scoped orders update immediately
        dash_done = await client.get("/delivery/dashboard", headers=partner_headers)
        assert dash_done.json()["counts"]["completed"] == 1
        assert dash_done.json()["counts"]["in_progress"] == 0
        assert len(dash_done.json()["active_deliveries"]) == 0

        completed_list = await client.get("/delivery/orders?scope=completed", headers=partner_headers)
        assert completed_list.status_code == 200
        assert any(o["id"] == str(order_1.id) and o["actual_delivery_date"] is not None for o in completed_list.json())

        completed_detail = await client.get(f"/delivery/orders/{order_1.id}", headers=partner_headers)
        assert completed_detail.status_code == 200
        assert completed_detail.json()["assignment"]["status"] == "completed"

        # Cash custody tracks collected separately from remitted (deposited = 0)
        cash_summary = await client.get("/delivery/cash/summary", headers=partner_headers)
        assert cash_summary.status_code == 200
        assert cash_summary.json()["collected_paise"] == order_1.total_paise
        assert cash_summary.json()["deposited_paise"] == 0
        assert cash_summary.json()["pending_paise"] == order_1.total_paise

        # Admin & Customer tracking sync
        admin_order = await client.get(f"/admin/orders/{order_1.id}", headers=admin_headers)
        assert admin_order.status_code == 200
        assert admin_order.json()["status"] == "delivered"
        assert admin_order.json()["payment_status"] == "paid"
        assert admin_order.json()["delivered_at"] is not None

        cust_tracking = await client.get(f"/orders/{order_1.id}/tracking", headers=customer_headers)
        assert cust_tracking.status_code == 200
        assert cust_tracking.json()["status"] == "delivered"
        assert cust_tracking.json()["actual_delivery_date"] is not None
    finally:
        await client.aclose()
        await db_session.rollback()
        app.dependency_overrides[get_db] = previous if previous is not None else get_db
        await _cleanup_committed(created_order_ids, created_partner_ids, product_id, original_stock)


@pytest.mark.asyncio
async def test_delivery_partner_failed_delivery_reschedule_and_idor(db_session, monkeypatch):
    admin, customer, addr, product = await _ensure_fixtures(db_session)
    order = await _create_order(db_session, customer, addr.id, product, method="cod")
    redelivery_otps: list[str] = []

    async def capture_redelivery_otp(_email: str, code: str, _order_number: str):
        redelivery_otps.append(code)

    monkeypatch.setattr("app.api.delivery_management.send_delivery_otp_email", capture_redelivery_otp)

    admin_headers = {"Authorization": f"Bearer {create_admin_token(str(admin.id))}"}
    client, previous = await _client_for_session(db_session)
    try:
        p1_id, p1_headers = await _create_and_login_partner(client, admin_headers, max_active=2)
        p2_id, p2_headers = await _create_and_login_partner(client, admin_headers, max_active=2)

        await _confirm_and_pack(client, admin_headers, order)
        assign_res = await client.post(
            f"/admin/delivery/orders/{order.id}/assign",
            headers=admin_headers,
            json={"partner_id": p1_id},
        )
        assert assign_res.status_code == 201
        v = assign_res.json()["version"]

        # IDOR protection: Partner 2 cannot view or act on Partner 1's order
        assert (await client.get(f"/delivery/orders/{order.id}", headers=p2_headers)).status_code == 404
        assert (
            await client.post(
                f"/delivery/orders/{order.id}/accept",
                headers=p2_headers,
                json={"expected_version": v},
            )
        ).status_code == 404

        acc = await client.post(f"/delivery/orders/{order.id}/accept", headers=p1_headers, json={"expected_version": v})
        pick = await client.post(f"/delivery/orders/{order.id}/pickup", headers=p1_headers, json={"expected_version": acc.json()["version"]})
        start = await client.post(f"/delivery/orders/{order.id}/start", headers=p1_headers, json={"expected_version": pick.json()["version"]})
        assert start.status_code == 200

        # Report failed delivery with required reason
        fail_res = await client.post(
            f"/delivery/orders/{order.id}/failed",
            headers=p1_headers,
            json={"expected_version": start.json()["version"], "note": "Customer unavailable"},
        )
        assert fail_res.status_code == 200, fail_res.text
        assert fail_res.json()["status"] == "failed"

        # Verify DB state: delivery_failed, still pending payment, reason persisted, no CODCollection
        await db_session.refresh(order)
        assert order.status == OrderStatus.delivery_failed
        assert order.payment_status != PaymentStatus.paid
        failed_assignment = await db_session.scalar(
            select(DeliveryAssignment).where(
                DeliveryAssignment.order_id == order.id,
                DeliveryAssignment.partner_id == uuid.UUID(p1_id),
            )
        )
        assert failed_assignment is not None
        assert failed_assignment.status == "failed"
        assert failed_assignment.failure_reason == "Customer unavailable"
        assert (await db_session.scalar(select(CODCollection.id).where(CODCollection.order_id == order.id))) is None

        failed_orders = await client.get("/delivery/orders?scope=failed", headers=p1_headers)
        assert failed_orders.status_code == 200
        assert len(failed_orders.json()) == 1
        assert failed_orders.json()[0]["assignment"]["failure_reason"] == "Customer unavailable"

        history_orders = await client.get("/delivery/orders?scope=history", headers=p1_headers)
        assert any(o["id"] == str(order.id) for o in history_orders.json())

        # Admin reassigns rescheduled failed order to Partner 2 -> Partner 2 completes delivery
        reassign_res = await client.post(
            f"/admin/delivery/orders/{order.id}/assign",
            headers=admin_headers,
            json={"partner_id": p2_id, "notes": "Redeliver next morning"},
        )
        assert reassign_res.status_code == 201, reassign_res.text
        v2 = reassign_res.json()["version"]
        acc2 = await client.post(f"/delivery/orders/{order.id}/accept", headers=p2_headers, json={"expected_version": v2})
        pick2 = await client.post(f"/delivery/orders/{order.id}/pickup", headers=p2_headers, json={"expected_version": acc2.json()["version"]})
        start2 = await client.post(f"/delivery/orders/{order.id}/start", headers=p2_headers, json={"expected_version": pick2.json()["version"]})
        assert start2.status_code == 200

        otp2_res = await client.post(f"/delivery/orders/{order.id}/request-otp", headers=p2_headers)
        assert otp2_res.status_code == 202
        detail2 = (await client.get(f"/delivery/orders/{order.id}", headers=p2_headers)).json()
        deliver2 = await client.post(
            f"/delivery/orders/{order.id}/deliver",
            headers=p2_headers,
            json={
                "expected_order_version": detail2["version"],
                "expected_assignment_version": detail2["assignment"]["version"],
                "idempotency_key": f"redeliv-{uuid.uuid4()}",
                "otp": redelivery_otps[-1],
                "cash_collected": True,
                "collected_amount_paise": order.total_paise,
            },
        )
        assert deliver2.status_code == 200
        assert deliver2.json()["order_status"] == "delivered"
        assert deliver2.json()["payment_status"] == "paid"
    finally:
        app.dependency_overrides[get_db] = previous if previous is not None else get_db


@pytest.mark.asyncio
async def test_online_unpaid_order_cannot_be_completed_by_delivery_partner(db_session):
    admin, customer, addr, product = await _ensure_fixtures(db_session)
    order = await _create_order(db_session, customer, addr.id, product, method="online")

    admin_headers = {"Authorization": f"Bearer {create_admin_token(str(admin.id))}"}
    client, previous = await _client_for_session(db_session)
    try:
        p_id, p_headers = await _create_and_login_partner(client, admin_headers, max_active=2)
        # Online unpaid order starts in payment_pending and cannot move to confirmed
        blocked_confirm = await client.post(
            f"/admin/orders/{order.id}/status",
            headers=admin_headers,
            json={"status": "confirmed", "expected_version": order.version},
        )
        assert blocked_confirm.status_code == 409

        # Even if an unpaid online order reached packed -> out_for_delivery, /deliver rejects it with 409
        order.status = OrderStatus.packed
        order.version += 1
        await db_session.flush()

        assign_res = await client.post(
            f"/admin/delivery/orders/{order.id}/assign",
            headers=admin_headers,
            json={"partner_id": p_id},
        )
        assert assign_res.status_code == 201
        acc = await client.post(f"/delivery/orders/{order.id}/accept", headers=p_headers, json={"expected_version": assign_res.json()["version"]})
        pick = await client.post(f"/delivery/orders/{order.id}/pickup", headers=p_headers, json={"expected_version": acc.json()["version"]})
        start = await client.post(f"/delivery/orders/{order.id}/start", headers=p_headers, json={"expected_version": pick.json()["version"]})
        assert start.status_code == 200

        detail = (await client.get(f"/delivery/orders/{order.id}", headers=p_headers)).json()
        otp_blocked = await client.post(f"/delivery/orders/{order.id}/request-otp", headers=p_headers)
        assert otp_blocked.status_code == 409
        blocked = await client.post(
            f"/delivery/orders/{order.id}/deliver",
            headers=p_headers,
            json={
                "expected_order_version": detail["version"],
                "expected_assignment_version": detail["assignment"]["version"],
                "idempotency_key": f"online-unpaid-{uuid.uuid4()}",
                "otp": "123456",
                "cash_collected": False,
            },
        )
        assert blocked.status_code == 409
    finally:
        app.dependency_overrides[get_db] = previous if previous is not None else get_db
