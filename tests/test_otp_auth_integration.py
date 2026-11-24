import asyncio
import uuid
from datetime import timedelta
import pytest
from httpx import AsyncClient
from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.clock import utc_now
from app.core.tokens import (
    create_customer_token,
    create_refresh_token,
    decode_token,
)
from app.models.user import User, Role
from app.models.otp import OTPCode
from app.services.otp_service import create_otp, verify_otp, _hash_otp
from app.services.auth_service import get_or_create_customer
from tests.conftest import db_test_session_maker


@pytest.mark.asyncio
async def test_new_customer_otp_request_endpoint(client: AsyncClient):
    """Test POST /auth/otp/request returns 202 and creates OTP."""
    test_email = f"req-test-{uuid.uuid4().hex[:8]}@example.com"
    try:
        req_res = await client.post("/auth/otp/request", json={"email": test_email})
        assert req_res.status_code == 202
        assert req_res.json() == {"message": "If the email exists, an OTP has been sent"}

        async with db_test_session_maker() as session:
            otp_row = (await session.execute(
                select(OTPCode).where(OTPCode.email == test_email)
            )).scalars().first()
            assert otp_row is not None
    finally:
        async with db_test_session_maker() as session:
            await session.execute(delete(OTPCode).where(OTPCode.email == test_email))
            await session.commit()


@pytest.mark.asyncio
async def test_otp_request_rate_limiting(client: AsyncClient):
    """Test that rate limiting enforces 5 requests per minute on /auth/otp/request."""
    test_emails = [f"rate-limit-{i}-{uuid.uuid4().hex[:6]}@example.com" for i in range(6)]
    try:
        # First 5 across distinct emails should succeed (202)
        for i in range(5):
            res = await client.post("/auth/otp/request", json={"email": test_emails[i]})
            assert res.status_code == 202

        # 6th from same IP should be throttled by slowapi (429)
        throttled_res = await client.post("/auth/otp/request", json={"email": test_emails[5]})
        assert throttled_res.status_code == 429
    finally:
        async with db_test_session_maker() as session:
            for email in test_emails:
                await session.execute(delete(OTPCode).where(OTPCode.email == email))
            await session.commit()


@pytest.mark.asyncio
async def test_otp_resend_cooldown(client: AsyncClient):
    """Test that requesting an OTP for the same email within 60s returns 429 cooldown."""
    test_email = f"cooldown-{uuid.uuid4().hex[:8]}@example.com"
    try:
        res1 = await client.post("/auth/otp/request", json={"email": test_email})
        assert res1.status_code == 202

        res2 = await client.post("/auth/otp/request", json={"email": test_email})
        assert res2.status_code == 429
        assert "wait before requesting another OTP" in res2.json()["detail"]
    finally:
        async with db_test_session_maker() as session:
            await session.execute(delete(OTPCode).where(OTPCode.email == test_email))
            await session.commit()


@pytest.mark.asyncio
async def test_new_customer_otp_login(client: AsyncClient, db_session: AsyncSession):
    """Test full OTP verification flow for a new customer."""
    test_email = f"new-cust-{uuid.uuid4().hex[:8]}@example.com"

    try:
        otp_code = await create_otp(db_session, test_email)
        await db_session.commit()

        # Verify OTP
        verify_res = await client.post("/auth/otp/verify", json={"email": test_email, "otp": otp_code})
        assert verify_res.status_code == 200, f"Expected 200, got {verify_res.status_code}: {verify_res.text}"
        data = verify_res.json()
        assert "access_token" in data
        assert "refresh_token" in data
        assert data["token_type"] == "bearer"

        # Check database customer record
        async with db_test_session_maker() as session:
            user = (await session.execute(
                select(User).where(User.email == test_email)
            )).scalar_one()
            assert user.role == Role.customer
            assert user.is_active is True
            assert user.full_name is None
            assert user.phone is None

        # Access /me with customer token
        me_res = await client.get("/me", headers={"Authorization": f"Bearer {data['access_token']}"})
        assert me_res.status_code == 200
        me_data = me_res.json()
        assert me_data["email"] == test_email
        assert me_data["role"] == "customer"
    finally:
        async with db_test_session_maker() as cleanup_session:
            await cleanup_session.execute(delete(OTPCode).where(OTPCode.email == test_email))
            await cleanup_session.execute(delete(User).where(User.email == test_email))
            await cleanup_session.commit()


@pytest.mark.asyncio
async def test_existing_customer_otp_login(client: AsyncClient, db_session: AsyncSession):
    """Test OTP flow for an existing customer preserves user profile data."""
    test_email = f"existing-cust-{uuid.uuid4().hex[:8]}@example.com"

    async with db_test_session_maker() as session:
        existing_user = User(
            role=Role.customer,
            email=test_email,
            full_name="Existing Customer",
            phone="9876543210",
            is_active=True,
        )
        session.add(existing_user)
        await session.commit()

    try:
        otp_code = await create_otp(db_session, test_email)
        await db_session.commit()

        verify_res = await client.post("/auth/otp/verify", json={"email": test_email, "otp": otp_code})
        assert verify_res.status_code == 200
        data = verify_res.json()

        me_res = await client.get("/me", headers={"Authorization": f"Bearer {data['access_token']}"})
        assert me_res.status_code == 200
        me_data = me_res.json()
        assert me_data["email"] == test_email
        assert me_data["full_name"] == "Existing Customer"
        assert me_data["phone"] == "9876543210"
    finally:
        async with db_test_session_maker() as cleanup_session:
            await cleanup_session.execute(delete(OTPCode).where(OTPCode.email == test_email))
            await cleanup_session.execute(delete(User).where(User.email == test_email))
            await cleanup_session.commit()


@pytest.mark.asyncio
async def test_invalid_otp_increments_attempts(client: AsyncClient, db_session: AsyncSession):
    """Test that invalid OTP code returns 401 and increments attempts in PostgreSQL."""
    test_email = f"invalid-otp-{uuid.uuid4().hex[:8]}@example.com"
    otp_code = await create_otp(db_session, test_email)
    await db_session.commit()

    try:
        wrong_otp = "000000" if otp_code != "000000" else "111111"
        res = await client.post("/auth/otp/verify", json={"email": test_email, "otp": wrong_otp})
        assert res.status_code == 401
        assert res.json()["detail"] == "Invalid or expired OTP"

        # Verify attempt counter in database was incremented and committed
        async with db_test_session_maker() as session:
            otp_row = (await session.execute(
                select(OTPCode).where(OTPCode.email == test_email)
            )).scalar_one_or_none()
            assert otp_row is not None
            assert otp_row.attempts == 1
    finally:
        async with db_test_session_maker() as cleanup_session:
            await cleanup_session.execute(delete(OTPCode).where(OTPCode.email == test_email))
            await cleanup_session.commit()


@pytest.mark.asyncio
async def test_brute_force_protection_max_attempts(client: AsyncClient, db_session: AsyncSession):
    """Test that reaching 5 failed attempts invalidates the OTP."""
    test_email = f"brute-force-{uuid.uuid4().hex[:8]}@example.com"
    otp_code = await create_otp(db_session, test_email)
    await db_session.commit()

    try:
        wrong_otp = "000000" if otp_code != "000000" else "111111"

        for i in range(5):
            res = await client.post("/auth/otp/verify", json={"email": test_email, "otp": wrong_otp})
            assert res.status_code == 401

        # Now try the correct OTP; it must fail because max attempts was reached
        res_correct = await client.post("/auth/otp/verify", json={"email": test_email, "otp": otp_code})
        assert res_correct.status_code == 401
    finally:
        async with db_test_session_maker() as cleanup_session:
            await cleanup_session.execute(delete(OTPCode).where(OTPCode.email == test_email))
            await cleanup_session.commit()


@pytest.mark.asyncio
async def test_expired_otp_rejected(client: AsyncClient):
    """Test that expired OTP is rejected with 401."""
    test_email = f"expired-otp-{uuid.uuid4().hex[:8]}@example.com"

    async with db_test_session_maker() as session:
        expired_otp = OTPCode(
            email=test_email,
            code_hash=_hash_otp("123456"),
            expires_at=utc_now() - timedelta(minutes=1),
            created_at=utc_now() - timedelta(minutes=6),
        )
        session.add(expired_otp)
        await session.commit()

    try:
        res = await client.post("/auth/otp/verify", json={"email": test_email, "otp": "123456"})
        assert res.status_code == 401
        assert res.json()["detail"] == "Invalid or expired OTP"
    finally:
        async with db_test_session_maker() as cleanup_session:
            await cleanup_session.execute(delete(OTPCode).where(OTPCode.email == test_email))
            await cleanup_session.commit()


@pytest.mark.asyncio
async def test_reused_otp_rejected(client: AsyncClient, db_session: AsyncSession):
    """Test that an already consumed OTP cannot be replayed."""
    test_email = f"reused-otp-{uuid.uuid4().hex[:8]}@example.com"
    otp_code = await create_otp(db_session, test_email)
    await db_session.commit()

    try:
        res1 = await client.post("/auth/otp/verify", json={"email": test_email, "otp": otp_code})
        assert res1.status_code == 200

        res2 = await client.post("/auth/otp/verify", json={"email": test_email, "otp": otp_code})
        assert res2.status_code == 401
        assert res2.json()["detail"] == "Invalid or expired OTP"
    finally:
        async with db_test_session_maker() as cleanup_session:
            await cleanup_session.execute(delete(OTPCode).where(OTPCode.email == test_email))
            await cleanup_session.execute(delete(User).where(User.email == test_email))
            await cleanup_session.commit()


@pytest.mark.asyncio
async def test_duplicate_customer_prevention():
    """Test that concurrent or repeated get_or_create_customer calls never create duplicates."""
    test_email = f"dup-test-{uuid.uuid4().hex[:8]}@example.com"

    try:
        async with db_test_session_maker() as session1:
            u1 = await get_or_create_customer(session1, test_email)
            await session1.commit()

        async with db_test_session_maker() as session2:
            u2 = await get_or_create_customer(session2, test_email)
            await session2.commit()

        assert u1.id == u2.id

        async with db_test_session_maker() as session:
            count = (await session.execute(
                select(User).where(User.email == test_email)
            )).scalars().all()
            assert len(count) == 1
    finally:
        async with db_test_session_maker() as cleanup_session:
            await cleanup_session.execute(delete(User).where(User.email == test_email))
            await cleanup_session.commit()


@pytest.mark.asyncio
async def test_concurrent_otp_verification():
    """Test concurrent verification of the same OTP allows only one to succeed."""
    test_email = f"concurrent-otp-{uuid.uuid4().hex[:8]}@example.com"

    async with db_test_session_maker() as session:
        otp_code = await create_otp(session, test_email)
        await session.commit()

    try:
        async def verify_task():
            async with db_test_session_maker() as sess:
                res = await verify_otp(sess, test_email, otp_code)
                await sess.commit()
                return res

        results = await asyncio.gather(verify_task(), verify_task())
        assert results.count(True) == 1
        assert results.count(False) == 1
    finally:
        async with db_test_session_maker() as cleanup_session:
            await cleanup_session.execute(delete(OTPCode).where(OTPCode.email == test_email))
            await cleanup_session.commit()


@pytest.mark.asyncio
async def test_inactive_customer_handling(client: AsyncClient, db_session: AsyncSession):
    """Test that deactivated customer cannot verify OTP or access protected routes."""
    test_email = f"inactive-cust-{uuid.uuid4().hex[:8]}@example.com"

    async with db_test_session_maker() as session:
        user = User(
            role=Role.customer,
            email=test_email,
            is_active=False,
        )
        session.add(user)
        await session.commit()
        user_id = str(user.id)

    try:
        otp_code = await create_otp(db_session, test_email)
        await db_session.commit()

        verify_res = await client.post("/auth/otp/verify", json={"email": test_email, "otp": otp_code})
        assert verify_res.status_code == 403
        assert verify_res.json()["detail"] == "Account is deactivated"

        token = create_customer_token(user_id)
        me_res = await client.get("/me", headers={"Authorization": f"Bearer {token}"})
        assert me_res.status_code == 401
    finally:
        async with db_test_session_maker() as cleanup_session:
            await cleanup_session.execute(delete(OTPCode).where(OTPCode.email == test_email))
            await cleanup_session.execute(delete(User).where(User.email == test_email))
            await cleanup_session.commit()


@pytest.mark.asyncio
async def test_admin_cannot_login_via_customer_otp(client: AsyncClient, db_session: AsyncSession):
    """Test that an admin account cannot authenticate via the customer OTP endpoint."""
    test_email = f"admin-probe-{uuid.uuid4().hex[:8]}@example.com"

    async with db_test_session_maker() as session:
        admin_user = User(
            role=Role.admin,
            username=f"admin_{uuid.uuid4().hex[:6]}",
            password_hash="fakehash",
            email=test_email,
            is_active=True,
        )
        session.add(admin_user)
        await session.commit()

    try:
        otp_code = await create_otp(db_session, test_email)
        await db_session.commit()

        verify_res = await client.post("/auth/otp/verify", json={"email": test_email, "otp": otp_code})
        assert verify_res.status_code == 403
        assert verify_res.json()["detail"] == "Admin accounts must authenticate via admin login"
    finally:
        async with db_test_session_maker() as cleanup_session:
            await cleanup_session.execute(delete(OTPCode).where(OTPCode.email == test_email))
            await cleanup_session.execute(delete(User).where(User.email == test_email))
            await cleanup_session.commit()


@pytest.mark.asyncio
async def test_token_generation_and_refresh(client: AsyncClient):
    """Test token generation, refresh token exchange, and logout."""
    test_user_id = str(uuid.uuid4())

    async with db_test_session_maker() as session:
        user = User(
            id=uuid.UUID(test_user_id),
            role=Role.customer,
            email=f"refresh-test-{uuid.uuid4().hex[:6]}@example.com",
            is_active=True,
        )
        session.add(user)
        await session.commit()

    try:
        ref_token = create_refresh_token(test_user_id, "customer")

        refresh_res = await client.post("/auth/refresh", json={"refresh_token": ref_token})
        assert refresh_res.status_code == 200
        ref_data = refresh_res.json()
        assert "access_token" in ref_data
        assert "refresh_token" in ref_data

        payload = decode_token(ref_data["access_token"])
        assert payload["sub"] == test_user_id
        assert payload["role"] == "customer"

        bad_res = await client.post("/auth/refresh", json={"refresh_token": ref_data["access_token"]})
        assert bad_res.status_code == 401

        logout_res = await client.post("/auth/logout")
        assert logout_res.status_code == 200
        assert logout_res.json()["message"] == "Successfully logged out"
    finally:
        async with db_test_session_maker() as cleanup_session:
            await cleanup_session.execute(delete(User).where(User.id == uuid.UUID(test_user_id)))
            await cleanup_session.commit()


@pytest.mark.asyncio
async def test_database_rollback_on_failed_operation():
    """Verify that a failed database transaction rolls back cleanly without leaving dirty state."""
    try:
        async with db_test_session_maker() as session:
            invalid_user = User(role=Role.customer, email=None)
            session.add(invalid_user)
            await session.commit()
    except Exception:
        pass

    async with db_test_session_maker() as session:
        users = (await session.execute(
            select(User).where(User.email.is_(None), User.role == Role.customer)
        )).scalars().all()
        assert len(users) == 0
