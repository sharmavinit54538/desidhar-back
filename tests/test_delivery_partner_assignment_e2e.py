"""End-to-end PostgreSQL integration tests for delivery partner assignment, eligibility, concurrency, and tracking."""
import asyncio
import uuid
from datetime import datetime, timezone

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
from app.models.payment import Payment
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


async def _ensure_303701_fixture(db_session):
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

    pin303701 = await db_session.scalar(select(Pincode).where(Pincode.pincode == "303701"))
    if not pin303701:
        pin303701 = Pincode(
            pincode="303701",
            area_name="Punana",
            city="Jaipur",
            state="Rajasthan",
            is_serviceable=True,
            delivery_fee_paise=0,
            min_order_paise=0,
            cod_available=True,
        )
        db_session.add(pin303701)
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
            full_name="Test Customer 303701",
            phone="9876543210",
            line1="12 Village Road",
            city="Jaipur",
            state="Rajasthan",
            pincode="303701",
            is_default=False,
        )
        db_session.add(addr)
        await db_session.flush()

    return admin, customer, addr, product


async def _place_cod_order(db_session, customer: User, address_id: uuid.UUID, product: Product) -> Order:
    cart = await db_session.scalar(select(Cart).where(Cart.user_id == customer.id))
    if cart is None:
        cart = Cart(user_id=customer.id)
        db_session.add(cart)
        await db_session.flush()
    cart.items.clear()
    cart.items.append(CartItem(product_id=product.id, quantity=1))
    await db_session.flush()

    order, error, _ = await place_order(
        db_session, customer, address_id, "cod", f"e2e-order-{uuid.uuid4()}"
    )
    assert error is None and order is not None
    return order


@pytest.mark.asyncio
async def test_eligibility_rules_pincode_303701_and_assignment_e2e(db_session):
    admin, customer, addr_303701, product = await _ensure_303701_fixture(db_session)
    order = await _place_cod_order(db_session, customer, addr_303701.id, product)
    extra_order = await _place_cod_order(db_session, customer, addr_303701.id, product)

    admin_headers = {"Authorization": f"Bearer {create_admin_token(str(admin.id))}"}
    customer_headers = {"Authorization": f"Bearer {create_customer_token(str(customer.id))}"}
    client, previous = await _client_for_session(db_session)
    try:
        # 1. Order not packed yet -> assignment must fail with 409
        p_eligible_res = await client.post(
            "/admin/delivery/partners",
            headers=admin_headers,
            json={
                "username": f"elig-{uuid.uuid4().hex[:8]}",
                "password": f"StrongPass-{uuid.uuid4().hex[:8]}",
                "full_name": "Eligible Rider 303701",
                "phone": "9811111111",
                "employee_id": f"EMP-{uuid.uuid4().hex[:8]}",
                "service_area": "Jaipur 303701",
                "service_pincodes": [" 303701 "],
                "max_active_deliveries": 3,
                "availability": "available",
            },
        )
        assert p_eligible_res.status_code == 201, p_eligible_res.text
        eligible_id = p_eligible_res.json()["user_id"]
        assert p_eligible_res.json()["service_pincodes"] == ["303701"]

        not_packed_assign = await client.post(
            f"/admin/delivery/orders/{order.id}/assign",
            headers=admin_headers,
            json={"partner_id": eligible_id},
        )
        assert not_packed_assign.status_code == 409

        # Confirm only -> still not packed -> must fail with 409
        conf_res = await client.post(
            f"/admin/orders/{order.id}/status",
            headers=admin_headers,
            json={"status": "confirmed", "expected_version": order.version},
        )
        assert conf_res.status_code == 200
        still_not_packed = await client.post(
            f"/admin/delivery/orders/{order.id}/assign",
            headers=admin_headers,
            json={"partner_id": eligible_id},
        )
        assert still_not_packed.status_code == 409

        # Pack both orders
        pack_res = await client.post(
            f"/admin/orders/{order.id}/status",
            headers=admin_headers,
            json={"status": "packed", "expected_version": conf_res.json()["version"]},
        )
        assert pack_res.status_code == 200

        c2 = await client.post(
            f"/admin/orders/{extra_order.id}/status",
            headers=admin_headers,
            json={"status": "confirmed", "expected_version": extra_order.version},
        )
        assert c2.status_code == 200
        p2 = await client.post(
            f"/admin/orders/{extra_order.id}/status",
            headers=admin_headers,
            json={"status": "packed", "expected_version": c2.json()["version"]},
        )
        assert p2.status_code == 200

        # 2. Create partners covering each negative eligibility rule
        p_wrong_pin = (
            await client.post(
                "/admin/delivery/partners",
                headers=admin_headers,
                json={
                    "username": f"pin-{uuid.uuid4().hex[:8]}",
                    "password": f"StrongPass-{uuid.uuid4().hex[:8]}",
                    "full_name": "Wrong Pin Rider",
                    "phone": "9822222222",
                    "employee_id": f"EMP-{uuid.uuid4().hex[:8]}",
                    "service_area": "Bengaluru",
                    "service_pincodes": ["560001"],
                    "max_active_deliveries": 3,
                    "availability": "available",
                },
            )
        ).json()["user_id"]

        p_offline = (
            await client.post(
                "/admin/delivery/partners",
                headers=admin_headers,
                json={
                    "username": f"off-{uuid.uuid4().hex[:8]}",
                    "password": f"StrongPass-{uuid.uuid4().hex[:8]}",
                    "full_name": "Offline Rider",
                    "phone": "9833333333",
                    "employee_id": f"EMP-{uuid.uuid4().hex[:8]}",
                    "service_area": "Jaipur 303701",
                    "service_pincodes": ["303701"],
                    "max_active_deliveries": 3,
                    "availability": "offline",
                },
            )
        ).json()["user_id"]

        p_inactive = (
            await client.post(
                "/admin/delivery/partners",
                headers=admin_headers,
                json={
                    "username": f"inact-{uuid.uuid4().hex[:8]}",
                    "password": f"StrongPass-{uuid.uuid4().hex[:8]}",
                    "full_name": "Inactive Rider",
                    "phone": "9844444444",
                    "employee_id": f"EMP-{uuid.uuid4().hex[:8]}",
                    "service_area": "Jaipur 303701",
                    "service_pincodes": ["303701"],
                    "max_active_deliveries": 3,
                    "availability": "available",
                },
            )
        ).json()["user_id"]
        await client.patch(f"/admin/delivery/partners/{p_inactive}/active?active=false", headers=admin_headers)

        p_suspended = (
            await client.post(
                "/admin/delivery/partners",
                headers=admin_headers,
                json={
                    "username": f"susp-{uuid.uuid4().hex[:8]}",
                    "password": f"StrongPass-{uuid.uuid4().hex[:8]}",
                    "full_name": "Suspended Rider",
                    "phone": "9855555555",
                    "employee_id": f"EMP-{uuid.uuid4().hex[:8]}",
                    "service_area": "Jaipur 303701",
                    "service_pincodes": ["303701"],
                    "max_active_deliveries": 3,
                    "availability": "available",
                },
            )
        ).json()["user_id"]
        await client.patch(f"/admin/delivery/partners/{p_suspended}/suspend?suspended=true", headers=admin_headers)

        p_full = (
            await client.post(
                "/admin/delivery/partners",
                headers=admin_headers,
                json={
                    "username": f"full-{uuid.uuid4().hex[:8]}",
                    "password": f"StrongPass-{uuid.uuid4().hex[:8]}",
                    "full_name": "Full Capacity Rider",
                    "phone": "9866666666",
                    "employee_id": f"EMP-{uuid.uuid4().hex[:8]}",
                    "service_area": "Jaipur 303701",
                    "service_pincodes": ["303701"],
                    "max_active_deliveries": 1,
                    "availability": "available",
                },
            )
        ).json()["user_id"]
        # Exhaust p_full's capacity using extra_order
        cap_fill = await client.post(
            f"/admin/delivery/orders/{extra_order.id}/assign",
            headers=admin_headers,
            json={"partner_id": p_full},
        )
        assert cap_fill.status_code == 201

        # 3. Check eligible-partners endpoint
        elig_res = await client.get(
            f"/admin/delivery/orders/{order.id}/eligible-partners",
            headers=admin_headers,
        )
        assert elig_res.status_code == 200, elig_res.text
        by_id = {row["user_id"]: row for row in elig_res.json()}

        assert by_id[eligible_id]["is_eligible"] is True
        assert by_id[eligible_id]["remaining_capacity"] == 3
        assert by_id[eligible_id]["phone"] == "9811111111"
        assert by_id[eligible_id]["service_area"] == "Jaipur 303701"

        assert by_id[p_wrong_pin]["is_eligible"] is False
        assert "outside partner's service area" in by_id[p_wrong_pin]["ineligibility_reason"].lower()

        assert by_id[p_offline]["is_eligible"] is False
        assert "not available" in by_id[p_offline]["ineligibility_reason"].lower()

        assert by_id[p_inactive]["is_eligible"] is False
        assert "inactive" in by_id[p_inactive]["ineligibility_reason"].lower()

        assert by_id[p_suspended]["is_eligible"] is False
        assert "suspended" in by_id[p_suspended]["ineligibility_reason"].lower()

        assert by_id[p_full]["is_eligible"] is False
        assert by_id[p_full]["remaining_capacity"] == 0
        assert "capacity" in by_id[p_full]["ineligibility_reason"].lower()

        # 4. Reject assignment to each ineligible partner
        assert (await client.post(f"/admin/delivery/orders/{order.id}/assign", headers=admin_headers, json={"partner_id": p_wrong_pin})).status_code == 422
        assert (await client.post(f"/admin/delivery/orders/{order.id}/assign", headers=admin_headers, json={"partner_id": p_offline})).status_code == 409
        assert (await client.post(f"/admin/delivery/orders/{order.id}/assign", headers=admin_headers, json={"partner_id": p_inactive})).status_code == 422
        assert (await client.post(f"/admin/delivery/orders/{order.id}/assign", headers=admin_headers, json={"partner_id": p_suspended})).status_code == 409
        assert (await client.post(f"/admin/delivery/orders/{order.id}/assign", headers=admin_headers, json={"partner_id": p_full})).status_code == 409

        # 5. Assign eligible partner to packed order
        assigned = await client.post(
            f"/admin/delivery/orders/{order.id}/assign",
            headers=admin_headers,
            json={"partner_id": eligible_id},
        )
        assert assigned.status_code == 201, assigned.text
        asg_data = assigned.json()
        assert asg_data["status"] == "assigned"
        assert asg_data["partner_name"] == "Eligible Rider 303701"
        assert asg_data["partner_phone"] == "9811111111"
        assert asg_data["assigned_at"] is not None
        assert len(asg_data["history"]) == 1

        # 6. Duplicate assignment prevention
        dup = await client.post(
            f"/admin/delivery/orders/{order.id}/assign",
            headers=admin_headers,
            json={"partner_id": eligible_id},
        )
        assert dup.status_code == 409

        # 7. Verify notification created for delivery partner
        notif = await db_session.scalar(
            select(OrderNotification).where(
                OrderNotification.order_id == order.id,
                OrderNotification.user_id == uuid.UUID(eligible_id),
                OrderNotification.event_type == "delivery_assignment",
            )
        )
        assert notif is not None
        assert order.order_number in notif.message

        # 8. Refresh admin order detail + assignment history
        refreshed_admin = await client.get(f"/admin/orders/{order.id}", headers=admin_headers)
        assert refreshed_admin.status_code == 200
        ref_json = refreshed_admin.json()
        assert ref_json["delivery_status"] == "assigned"
        assert ref_json["active_assignment"]["partner_name"] == "Eligible Rider 303701"
        assert ref_json["active_assignment"]["partner_phone"] == "9811111111"

        # 9. Customer order tracking updated WITHOUT exposing partner PII
        cust_order = await client.get(f"/orders/{order.id}", headers=customer_headers)
        assert cust_order.status_code == 200
        cust_json = cust_order.json()
        assert cust_json["delivery_status"] == "assigned"
        assert cust_json["estimated_delivery_date"] is not None
        assert "active_assignment" not in cust_json
        assert "Eligible Rider 303701" not in cust_order.text
        assert "9811111111" not in cust_order.text

        cust_track = await client.get(f"/orders/{order.id}/tracking", headers=customer_headers)
        assert cust_track.status_code == 200
        track_json = cust_track.json()
        assert track_json["delivery_status"] == "assigned"
        assert track_json["estimated_delivery_date"] is not None
        assert "Eligible Rider 303701" not in cust_track.text

        # 10. Cancelled / delivered / returned order assignment prevention
        cancelled_order = await _place_cod_order(db_session, customer, addr_303701.id, product)
        cancel_res = await client.post(
            f"/admin/orders/{cancelled_order.id}/status",
            headers=admin_headers,
            json={"status": "cancelled", "expected_version": cancelled_order.version, "note": "No longer needed"},
        )
        assert cancel_res.status_code == 200
        assert (
            await client.post(
                f"/admin/delivery/orders/{cancelled_order.id}/assign",
                headers=admin_headers,
                json={"partner_id": eligible_id},
            )
        ).status_code == 409
    finally:
        await client.aclose()
        if previous is None:
            app.dependency_overrides.pop(get_db, None)
        else:
            app.dependency_overrides[get_db] = previous


@pytest.mark.asyncio
async def test_reassignment_failed_delivery_reschedule_and_partner_management_e2e(db_session, monkeypatch):
    admin, customer, addr_303701, product = await _ensure_303701_fixture(db_session)
    order = await _place_cod_order(db_session, customer, addr_303701.id, product)

    admin_headers = {"Authorization": f"Bearer {create_admin_token(str(admin.id))}"}
    customer_headers = {"Authorization": f"Bearer {create_customer_token(str(customer.id))}"}
    client, previous = await _client_for_session(db_session)
    try:
        # Pack order
        c1 = await client.post(f"/admin/orders/{order.id}/status", headers=admin_headers, json={"status": "confirmed", "expected_version": order.version})
        p1 = await client.post(f"/admin/orders/{order.id}/status", headers=admin_headers, json={"status": "packed", "expected_version": c1.json()["version"]})
        assert p1.status_code == 200

        # Create 2 partners via admin API, edit partner 1, test availability & view detail
        pw1 = f"PartnerOne-{uuid.uuid4().hex[:8]}"
        pw2 = f"PartnerTwo-{uuid.uuid4().hex[:8]}"
        u1 = f"dp1-{uuid.uuid4().hex[:8]}"
        u2 = f"dp2-{uuid.uuid4().hex[:8]}"

        r1 = await client.post(
            "/admin/delivery/partners",
            headers=admin_headers,
            json={
                "username": u1,
                "password": pw1,
                "full_name": "Rider One",
                "phone": "9810101010",
                "employee_id": f"DPR1-{uuid.uuid4().hex[:6]}",
                "service_pincodes": ["560001"],
                "max_active_deliveries": 2,
            },
        )
        assert r1.status_code == 201
        id1 = r1.json()["user_id"]

        # Edit partner 1 to cover 303701, set capacity=4, service_area, and availability=available
        edit_res = await client.patch(
            f"/admin/delivery/partners/{id1}",
            headers=admin_headers,
            json={
                "full_name": "Rider One Updated",
                "service_area": "Jaipur Rural",
                "service_pincodes": [" 303701 ", "302001"],
                "max_active_deliveries": 4,
                "availability": "available",
            },
        )
        assert edit_res.status_code == 200, edit_res.text
        assert edit_res.json()["full_name"] == "Rider One Updated"
        assert edit_res.json()["service_pincodes"] == ["303701", "302001"]
        assert edit_res.json()["max_active_deliveries"] == 4
        assert edit_res.json()["availability"] == "available"

        r2 = await client.post(
            "/admin/delivery/partners",
            headers=admin_headers,
            json={
                "username": u2,
                "password": pw2,
                "full_name": "Rider Two",
                "phone": "9820202020",
                "employee_id": f"DPR2-{uuid.uuid4().hex[:6]}",
                "service_area": "Jaipur 303701",
                "service_pincodes": ["303701"],
                "max_active_deliveries": 3,
                "availability": "available",
            },
        )
        assert r2.status_code == 201
        id2 = r2.json()["user_id"]

        # Assign to Rider 1
        a1 = await client.post(f"/admin/delivery/orders/{order.id}/assign", headers=admin_headers, json={"partner_id": id1})
        assert a1.status_code == 201

        # Same-partner reassign rejected
        same_re = await client.post(f"/admin/delivery/orders/{order.id}/reassign", headers=admin_headers, json={"partner_id": id1})
        assert same_re.status_code == 409

        # Reassign to Rider 2
        a2 = await client.post(f"/admin/delivery/orders/{order.id}/reassign", headers=admin_headers, json={"partner_id": id2})
        assert a2.status_code == 200, a2.text
        assert a2.json()["partner_id"] == id2

        # Partner 1 now has 0 active orders and Partner 2 has 1 active order
        d1 = await client.get(f"/admin/delivery/partners/{id1}", headers=admin_headers)
        d2 = await client.get(f"/admin/delivery/partners/{id2}", headers=admin_headers)
        assert d1.json()["active_assignments"] == 0
        assert len(d2.json()["assigned_orders"]) == 1

        # Login Partner 2, check notifications, accept -> pickup -> start -> failed
        login2 = await client.post("/delivery/auth/login", json={"username": u2, "password": pw2})
        assert login2.status_code == 200
        h2 = {"Authorization": f"Bearer {login2.json()['access_token']}"}
        notifs2 = await client.get("/delivery/notifications", headers=h2)
        assert notifs2.status_code == 200
        assert any(order.order_number in n["message"] for n in notifs2.json())

        asg_v = a2.json()["version"]
        acc = await client.post(f"/delivery/orders/{order.id}/accept", headers=h2, json={"expected_version": asg_v})
        assert acc.status_code == 200
        pick = await client.post(f"/delivery/orders/{order.id}/pickup", headers=h2, json={"expected_version": acc.json()["version"]})
        assert pick.status_code == 200 and pick.json()["fulfillment_status"] == "shipped"
        start = await client.post(f"/delivery/orders/{order.id}/start", headers=h2, json={"expected_version": pick.json()["version"]})
        assert start.status_code == 200 and start.json()["fulfillment_status"] == "out_for_delivery"

        # Verify customer tracking at out_for_delivery
        t_ofd = await client.get(f"/orders/{order.id}/tracking", headers=customer_headers)
        assert t_ofd.status_code == 200 and t_ofd.json()["status"] == "out_for_delivery"

        fail = await client.post(
            f"/delivery/orders/{order.id}/failed",
            headers=h2,
            json={"expected_version": start.json()["version"], "note": "Customer unavailable"},
        )
        assert fail.status_code == 200 and fail.json()["fulfillment_status"] == "delivery_failed"

        # Reschedule failed delivery by reassigning to Partner 1
        re_fail = await client.post(
            f"/admin/delivery/orders/{order.id}/reassign",
            headers=admin_headers,
            json={"partner_id": id1},
        )
        assert re_fail.status_code == 200, re_fail.text
        assert re_fail.json()["status"] == "assigned"

        # Partner 1 completes rescheduled delivery
        login1 = await client.post("/delivery/auth/login", json={"username": u1, "password": pw1})
        assert login1.status_code == 200
        h1 = {"Authorization": f"Bearer {login1.json()['access_token']}"}

        acc1 = await client.post(f"/delivery/orders/{order.id}/accept", headers=h1, json={"expected_version": re_fail.json()["version"]})
        pick1 = await client.post(f"/delivery/orders/{order.id}/pickup", headers=h1, json={"expected_version": acc1.json()["version"]})
        start1 = await client.post(f"/delivery/orders/{order.id}/start", headers=h1, json={"expected_version": pick1.json()["version"]})
        assert start1.status_code == 200 and start1.json()["fulfillment_status"] == "out_for_delivery"

        det1 = (await client.get(f"/delivery/orders/{order.id}", headers=h1)).json()
        col = await client.post(
            f"/delivery/orders/{order.id}/collect-payment",
            headers=h1,
            json={
                "expected_order_version": det1["version"],
                "expected_assignment_version": det1["assignment"]["version"],
                "idempotency_key": f"cod-{uuid.uuid4()}",
                "amount_paise": det1["outstanding_amount_paise"],
                "method": "cash",
            },
        )
        assert col.status_code == 200

        sent = {}
        async def capture_otp(email, code, order_number):
            sent["code"] = code
        monkeypatch.setattr("app.api.delivery_management.send_delivery_otp_email", capture_otp)
        assert (await client.post(f"/delivery/orders/{order.id}/request-otp", headers=h1)).status_code == 202
        done = await client.post(f"/delivery/orders/{order.id}/verify-otp", headers=h1, json={"otp": sent["code"]})
        assert done.status_code == 200 and done.json()["order_status"] == "delivered"

        # Customer tracking reflects delivered
        t_deliv = await client.get(f"/orders/{order.id}/tracking", headers=customer_headers)
        assert t_deliv.status_code == 200
        assert t_deliv.json()["status"] == "delivered"
        assert t_deliv.json()["actual_delivery_date"] is not None

        # Partner 1 detail now shows completed delivery & history; soft-delete works once no active orders
        d1_after = await client.get(f"/admin/delivery/partners/{id1}", headers=admin_headers)
        assert d1_after.status_code == 200
        assert d1_after.json()["completed_deliveries"] == 1
        assert len(d1_after.json()["completed_orders"]) == 1
        assert len(d1_after.json()["assignment_history"]) >= 4

        del_res = await client.delete(f"/admin/delivery/partners/{id1}", headers=admin_headers)
        assert del_res.status_code == 200
        assert del_res.json()["deleted_at"] is not None
        assert (await client.post("/delivery/auth/login", json={"username": u1, "password": pw1})).status_code == 401
    finally:
        await client.aclose()
        if previous is None:
            app.dependency_overrides.pop(get_db, None)
        else:
            app.dependency_overrides[get_db] = previous


@pytest.mark.asyncio
async def test_empty_eligible_partners_list_when_none_exist(db_session):
    admin, customer, addr_303701, product = await _ensure_303701_fixture(db_session)
    order = await _place_cod_order(db_session, customer, addr_303701.id, product)

    # Mark all existing profiles deleted inside this rolled-back session
    profiles = (await db_session.execute(select(DeliveryPartnerProfile))).scalars().all()
    now = datetime.now(timezone.utc)
    for prof in profiles:
        prof.deleted_at = now
    await db_session.flush()

    admin_headers = {"Authorization": f"Bearer {create_admin_token(str(admin.id))}"}
    client, previous = await _client_for_session(db_session)
    try:
        res = await client.get(f"/admin/delivery/orders/{order.id}/eligible-partners", headers=admin_headers)
        assert res.status_code == 200
        assert res.json() == []
    finally:
        await client.aclose()
        if previous is None:
            app.dependency_overrides.pop(get_db, None)
        else:
            app.dependency_overrides[get_db] = previous


@pytest.mark.asyncio
async def test_concurrent_assignments_and_database_persistence_across_requests():
    """Verify real committed PostgreSQL persistence, page refresh reads, and race-free capacity/order locks."""
    created_order_ids: list[uuid.UUID] = []
    created_partner_ids: list[uuid.UUID] = []

    async with db_test_session_maker() as setup_db:
        admin, customer, addr_303701, product = await _ensure_303701_fixture(setup_db)
        order_1 = await _place_cod_order(setup_db, customer, addr_303701.id, product)
        order_2 = await _place_cod_order(setup_db, customer, addr_303701.id, product)
        created_order_ids.extend([order_1.id, order_2.id])
        admin_id = admin.id
        admin_headers = {"Authorization": f"Bearer {create_admin_token(str(admin_id))}"}
        await setup_db.commit()

    # Use default dependency override (real committed sessions per request)
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            # Create two partners (P1 capacity=1, P2 capacity=1)
            for idx in (1, 2):
                p_res = await client.post(
                    "/admin/delivery/partners",
                    headers=admin_headers,
                    json={
                        "username": f"conc-{idx}-{uuid.uuid4().hex[:8]}",
                        "password": f"StrongConc-{uuid.uuid4().hex[:8]}",
                        "full_name": f"Concurrent Rider {idx}",
                        "phone": f"989000000{idx}",
                        "employee_id": f"CONC-{idx}-{uuid.uuid4().hex[:6]}",
                        "service_area": "Jaipur 303701",
                        "service_pincodes": ["303701"],
                        "max_active_deliveries": 1,
                        "availability": "available",
                    },
                )
                assert p_res.status_code == 201, p_res.text
                created_partner_ids.append(uuid.UUID(p_res.json()["user_id"]))

            # Pack both orders
            for oid in created_order_ids:
                o_detail = (await client.get(f"/admin/orders/{oid}", headers=admin_headers)).json()
                c_res = await client.post(
                    f"/admin/orders/{oid}/status",
                    headers=admin_headers,
                    json={"status": "confirmed", "expected_version": o_detail["version"]},
                )
                assert c_res.status_code == 200
                p_res = await client.post(
                    f"/admin/orders/{oid}/status",
                    headers=admin_headers,
                    json={"status": "packed", "expected_version": c_res.json()["version"]},
                )
                assert p_res.status_code == 200

            p1_id, p2_id = [str(pid) for pid in created_partner_ids]

            # Race 1: Concurrent assignment of SAME order_1 to different partners -> exactly 1 succeeds
            r_same_order = await asyncio.gather(
                client.post(f"/admin/delivery/orders/{order_1.id}/assign", headers=admin_headers, json={"partner_id": p1_id}),
                client.post(f"/admin/delivery/orders/{order_1.id}/assign", headers=admin_headers, json={"partner_id": p2_id}),
            )
            statuses_1 = sorted(r.status_code for r in r_same_order)
            assert statuses_1 == [201, 409], f"Expected [201, 409], got {statuses_1}: {[r.text for r in r_same_order]}"

            # Check which partner won order_1, then free or test Race 2 on fresh partner capacity=1
            p3_res = await client.post(
                "/admin/delivery/partners",
                headers=admin_headers,
                json={
                    "username": f"conc-3-{uuid.uuid4().hex[:8]}",
                    "password": f"StrongConc-{uuid.uuid4().hex[:8]}",
                    "full_name": "Concurrent Rider 3",
                    "phone": "9890000003",
                    "employee_id": f"CONC-3-{uuid.uuid4().hex[:6]}",
                    "service_area": "Jaipur 303701",
                    "service_pincodes": ["303701"],
                    "max_active_deliveries": 1,
                    "availability": "available",
                },
            )
            assert p3_res.status_code == 201
            p3_id = p3_res.json()["user_id"]
            created_partner_ids.append(uuid.UUID(p3_id))

            # Create another packed order_3 so we can race two distinct packed orders against p3 (capacity=1)
            async with db_test_session_maker() as setup_db2:
                _, customer2, addr2, prod2 = await _ensure_303701_fixture(setup_db2)
                order_3 = await _place_cod_order(setup_db2, customer2, addr2.id, prod2)
                created_order_ids.append(order_3.id)
                await setup_db2.commit()

            o3_detail = (await client.get(f"/admin/orders/{order_3.id}", headers=admin_headers)).json()
            c3 = await client.post(f"/admin/orders/{order_3.id}/status", headers=admin_headers, json={"status": "confirmed", "expected_version": o3_detail["version"]})
            p3 = await client.post(f"/admin/orders/{order_3.id}/status", headers=admin_headers, json={"status": "packed", "expected_version": c3.json()["version"]})
            assert p3.status_code == 200

            # Race 2: Concurrent assignment of order_2 and order_3 to SAME capacity=1 partner p3 -> exactly 1 succeeds
            r_same_partner = await asyncio.gather(
                client.post(f"/admin/delivery/orders/{order_2.id}/assign", headers=admin_headers, json={"partner_id": p3_id}),
                client.post(f"/admin/delivery/orders/{order_3.id}/assign", headers=admin_headers, json={"partner_id": p3_id}),
            )
            statuses_2 = sorted(r.status_code for r in r_same_partner)
            assert statuses_2 == [201, 409], f"Expected [201, 409], got {statuses_2}: {[r.text for r in r_same_partner]}"

            # Verify committed DB state & page refresh persistence across fresh sessions
            p3_detail = await client.get(f"/admin/delivery/partners/{p3_id}", headers=admin_headers)
            assert p3_detail.status_code == 200
            assert p3_detail.json()["active_assignments"] == 1
            assert p3_detail.json()["remaining_capacity"] == 0

            o1_refresh = await client.get(f"/admin/orders/{order_1.id}", headers=admin_headers)
            assert o1_refresh.status_code == 200
            assert o1_refresh.json()["active_assignment"] is not None
    finally:
        # Clean up committed test rows so database remains clean
        async with db_test_session_maker() as cleanup:
            if created_order_ids:
                await cleanup.execute(delete(DeliveryOTP).where(DeliveryOTP.order_id.in_(created_order_ids)))
                await cleanup.execute(delete(CODCollection).where(CODCollection.order_id.in_(created_order_ids)))
                await cleanup.execute(delete(DeliveryAssignmentHistory).where(DeliveryAssignmentHistory.order_id.in_(created_order_ids)))
                await cleanup.execute(delete(DeliveryAssignment).where(DeliveryAssignment.order_id.in_(created_order_ids)))
                await cleanup.execute(delete(OrderNotification).where(OrderNotification.order_id.in_(created_order_ids)))
                await cleanup.execute(delete(OrderAuditLog).where(OrderAuditLog.order_id.in_(created_order_ids)))
                await cleanup.execute(delete(OrderStatusHistory).where(OrderStatusHistory.order_id.in_(created_order_ids)))
                await cleanup.execute(delete(InventoryTransaction).where(InventoryTransaction.order_id.in_(created_order_ids)))
                await cleanup.execute(delete(Payment).where(Payment.order_id.in_(created_order_ids)))
                await cleanup.execute(delete(OrderItem).where(OrderItem.order_id.in_(created_order_ids)))
                await cleanup.execute(delete(Order).where(Order.id.in_(created_order_ids)))
            if created_partner_ids:
                await cleanup.execute(delete(DeliveryPartnerProfile).where(DeliveryPartnerProfile.user_id.in_(created_partner_ids)))
                await cleanup.execute(delete(User).where(User.id.in_(created_partner_ids)))
            await cleanup.commit()
