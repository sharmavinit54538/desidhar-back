# DesiDhar E-Commerce — Database Schema & OTP Authentication Permanent Fix Report

## Executive Summary

A comprehensive architectural and security audit was conducted on the DesiDhar e-commerce backend to permanently resolve database schema drift, Alembic migration bottlenecks, and production-blocking HTTP 500 errors during OTP authentication.

All database schema discrepancies across all 19 SQLAlchemy ORM models were audited, resolved, and verified against the live PostgreSQL database. The OTP authentication pipeline was completely re-engineered to be transactional, resistant to race conditions, protected against brute force, and secured against privilege escalation.

---

## 1. Root Cause Analysis

### 1.1 The Primary Production Blocker (`column users.full_name does not exist`)
- **Root Cause:** A prior commit introduced `full_name` and `phone` attributes to the SQLAlchemy `User` model (`app/models/user.py`) and generated migration `d8e4c92a710f_user_profile.py`. However, the migration was **never applied** to the active PostgreSQL database.
- **Trigger:** When `POST /auth/otp/verify` was invoked, `get_or_create_customer()` in `app/services/auth_service.py` executed `select(User).where(User.email == email_lower)`. Because SQLAlchemy selects all mapped columns on the model, `asyncpg` issued a query requesting `users.full_name` and `users.phone`.
- **Outcome:** PostgreSQL returned `UndefinedColumnError: column users.full_name does not exist`, terminating the request with HTTP 500 Internal Server Error.

### 1.2 Secondary Schema Inconsistencies Discovered
During the comprehensive schema audit against PostgreSQL `desidhar`:
- **Missing Check Constraints on `products`:** When columns `cost_price_paise`, `gst_rate_percent`, and `max_qty_per_order` were added in migration `b5d58428f1bc`, the associated database check constraints defined in `Product.__table_args__` were omitted:
  - `ck_cost_price_paise_non_negative` (`cost_price_paise >= 0`)
  - `ck_gst_rate_percent_range` (`gst_rate_percent >= 0 AND gst_rate_percent <= 100`)
  - `ck_max_qty_per_order_positive` (`max_qty_per_order > 0`)

### 1.3 Critical Authentication & Security Vulnerabilities Discovered
1. **Brute-Force Counter Rolled Back on 401:** In `verify_otp`, when an incorrect OTP code was submitted, `otp_code.attempts += 1` was incremented in the session. However, because `verify_otp_endpoint` raised `HTTPException(401)`, the session context manager in `app/core/db.py` rolled back the transaction on exception. This wiped out the attempt increment, allowing an attacker to attempt infinite guesses without hitting the `MAX_ATTEMPTS = 5` limit.
2. **Missing Row-Level Locking (Concurrent Verification Race Condition):** `verify_otp` queried `OTPCode` without `with_for_update()`. Two concurrent requests with the same valid OTP could both read `consumed_at IS NULL` simultaneously, validating the code twice before marking it consumed.
3. **Privilege Escalation Risk:** `verify_otp_endpoint` did not verify whether the authenticated user had `role == Role.customer`. If an administrator had an email address in `users`, requesting an OTP for that email and verifying it would yield a customer JWT token for an admin user account.
4. **Inactive Account Bypass:** `verify_otp_endpoint` did not check `user.is_active`, allowing deactivated or suspended customer accounts to authenticate and receive valid tokens.
5. **Race Condition in Customer Creation:** `get_or_create_customer` had no concurrency handling around `session.add(user)`. Two parallel OTP verifications for the same new user email would trigger an unhandled `IntegrityError` on the unique email constraint, returning a 500 error instead of resolving gracefully.
6. **Plaintext OTP Logging:** `send_otp_email()` in `app/services/email_service.py` explicitly printed raw plaintext OTP codes to `stdout` (`print(f"[DEV] OTP for {email}: {otp}")`), violating security standards.

---

## 2. All Discovered Schema Mismatches & Audit Results

Every SQLAlchemy ORM model table was inspected and compared with PostgreSQL information schema using SQLAlchemy's `inspect(engine)`:

| Table Name | ORM Status | PostgreSQL Status | Discrepancies Discovered | Resolution |
| :--- | :--- | :--- | :--- | :--- |
| `users` | 12 mapped columns | 10 columns present | Missing `full_name` VARCHAR(100), `phone` VARCHAR(15) | Applied migration `d8e4c92a710f` with data backfill |
| `products` | 19 mapped columns + constraints | 19 columns present | Missing 3 check constraints (`ck_cost_price_paise_non_negative`, `ck_gst_rate_percent_range`, `ck_max_qty_per_order_positive`) | Added migration `f47a1928bc01` |
| `otp_codes` | 7 mapped columns | 7 columns present | None | Aligned |
| `categories` | 7 mapped columns | 7 columns present | None | Aligned |
| `product_images` | 4 mapped columns | 4 columns present | None | Aligned |
| `pincodes` | 13 mapped columns | 13 columns present | None | Aligned |
| `product_pincodes` | 2 mapped columns | 2 columns present | None | Aligned |
| `addresses` | 13 mapped columns | 13 columns present | None | Aligned |
| `carts` | 4 mapped columns | 4 columns present | None | Aligned |
| `cart_items` | 4 mapped columns | 4 columns present | None | Aligned |
| `coupons` | 13 mapped columns | 13 columns present | None | Aligned |
| `coupon_redemptions` | 5 mapped columns | 5 columns present | None | Aligned |
| `orders` | 25 mapped columns | 25 columns present | None | Aligned |
| `order_items` | 14 mapped columns | 14 columns present | None | Aligned |
| `order_status_history`| 6 mapped columns | 6 columns present | None | Aligned |
| `payments` | 11 mapped columns | 11 columns present | None | Aligned |
| `refunds` | 9 mapped columns | 9 columns present | None | Aligned |
| `payment_methods` | 11 mapped columns | 11 columns present | None | Aligned |

---

## 3. Database Changes & New Migration Revisions

### 3.1 Migration `d8e4c92a710f_user_profile.py` (Updated & Applied)
- Added `users.full_name` (`VARCHAR(100)`, nullable)
- Added `users.phone` (`VARCHAR(15)`, nullable)
- **Safe Data Backfill:** Automatically backfilled existing customer names and mobile numbers from their active default addresses without overwriting pre-existing data:
  ```sql
  UPDATE users u
  SET full_name = COALESCE(u.full_name, a.full_name),
      phone = COALESCE(u.phone, a.phone)
  FROM addresses a
  WHERE a.user_id = u.id AND a.is_default = true AND a.deleted_at IS NULL;
  ```

### 3.2 New Migration `f47a1928bc01_product_check_constraints.py` (Created & Applied)
- Revision ID: `f47a1928bc01`
- Revises: `d8e4c92a710f`
- Implemented `ck_cost_price_paise_non_negative` check constraint on `products`
- Implemented `ck_gst_rate_percent_range` check constraint on `products`
- Implemented `ck_max_qty_per_order_positive` check constraint on `products`
- Full bidirectional support (`upgrade` and `downgrade`)

### 3.3 Verification Commands Output
```text
$ python -m alembic current
INFO  [alembic.runtime.migration] Context impl PostgresqlImpl.
INFO  [alembic.runtime.migration] Will assume transactional DDL.
f47a1928bc01 (head)

$ python -m alembic heads
f47a1928bc01 (head)

$ python -m alembic check
INFO  [alembic.runtime.migration] Context impl PostgresqlImpl.
INFO  [alembic.runtime.migration] Will assume transactional DDL.
No new upgrade operations detected.
```

---

## 4. All Fixed Authentication Bugs & Security Improvements

### 4.1 OTP Authentication Flow Fixes
1. **Transactional OTP Verification & Attempt Persistence:**
   - In `app/services/otp_service.py`, `verify_otp` locks the record using `.with_for_update()`.
   - On failed verification, `otp_code.attempts` is incremented and explicitly committed (`await session.commit()`), ensuring brute-force attempt counters persist even when the API controller raises HTTP 401.
   - If attempts exceed 5, the OTP code is deleted/invalidated.
2. **Replay Attack Prevention:**
   - On valid verification, `otp_code.consumed_at` is set to `utc_now()`.
   - Subsequent calls using the same OTP are immediately rejected (401 Unauthorized).
3. **Concurrent Registration & Duplicate Customer Prevention:**
   - `get_or_create_customer()` in `app/services/auth_service.py` uses nested transaction savepoints (`async with session.begin_nested():`) to catch concurrent `IntegrityError` on unique email constraints and fetch the newly created customer safely without returning HTTP 500.
4. **Account Inactivity Enforcement:**
   - `POST /auth/otp/verify` verifies `if not user.is_active:` and returns `403 Forbidden` (`Account is deactivated`).
   - Authenticated dependencies (`get_current_user`) verify active status before allowing access.
5. **Privilege Boundary Protection:**
   - `POST /auth/otp/verify` verifies `if user.role != Role.customer:` and raises `403 Forbidden` (`Admin accounts must authenticate via admin login`), eliminating admin privilege bypass.
6. **Input Normalization:**
   - Pydantic models `OTPRequest` and `OTPVerify` now normalize emails automatically (`mode="before"` field validators) with `.strip().lower()`.
7. **Refresh Token Flow Implementation:**
   - Implemented `POST /auth/refresh` accepting `{"refresh_token": "..."}`.
   - Tokens include explicit `"type": "refresh"` vs `"type": "access"` claims to prevent token substitution attacks.
   - Access tokens cannot be presented as refresh tokens and vice-versa.
   - Added `POST /auth/logout` endpoint returning 200 OK.
8. **Sensitive Data Protection:**
   - Removed plaintext OTP printing in `app/services/email_service.py`. Logging is sanitized and never records passwords, OTPs, or tokens.
   - Failed database operations during authentication rollback the session and return generic error details to prevent internal stack trace leaks.

---

## 5. Modified & Created Files

| File | Change Type | Summary of Changes |
| :--- | :--- | :--- |
| `alembic/versions/d8e4c92a710f_user_profile.py` | Modified | Added safe customer address backfill logic on upgrade. |
| `alembic/versions/f47a1928bc01_product_check_constraints.py` | Created | Added migration for missing `products` table check constraints. |
| `app/core/config.py` | Modified | Robust multi-path `.env` resolution for virtualenv and scripts. |
| `app/core/tokens.py` | Modified | Added `create_refresh_token()`, `decode_refresh_token()`, and token type guards. |
| `app/schemas/auth.py` | Modified | Email normalization validators, `RefreshTokenRequest`, `refresh_token` in `TokenResponse`. |
| `app/services/otp_service.py` | Modified | `with_for_update()` locking, attempt counter commit on failure, brute-force checks. |
| `app/services/auth_service.py` | Modified | Concurrency-safe customer creation using savepoints, role validation. |
| `app/services/email_service.py` | Modified | Sanitized logging, removed raw OTP `stdout` printing. |
| `app/api/auth.py` | Modified | Added `/auth/otp/resend`, `/auth/refresh`, `/auth/logout`, inactive & role guards, transaction rollback. |
| `app/api/admin.py` | Modified | Added refresh token to admin `TokenResponse`. |
| `app/main.py` | Modified | Registered `auth_router` for `/auth/refresh` and `/auth/logout`. |
| `requirements.txt` | Modified | Added `pytest`, `pytest-asyncio`, and `httpx`. |
| `pytest.ini` | Created | Configured asyncio mode and test loop fixture scope. |
| `tests/conftest.py` | Created | Provided isolated `NullPool` testing session maker and automatic limiter reset. |
| `tests/test_database_migrations.py` | Created | Integration tests for migration heads, current state, and schema inspection. |
| `tests/test_otp_auth_integration.py` | Created | Real PostgreSQL integration tests covering all OTP auth requirements and edge cases. |
| `tests/test_api_regression.py` | Created | Regression tests covering products, categories, addresses, pincodes, cart, and payment methods. |
| `scripts/audit_schema.py` | Created | Reusable full schema comparison utility between ORM metadata and PostgreSQL. |

---

## 6. Actual Test Results

Executed with: `python -m pytest -v` against the live PostgreSQL database.

```text
============================= test session starts =============================
platform win32 -- Python 3.14.3, pytest-9.2.0, pluggy-1.7.0 -- C:\Users\Dell\OneDrive\Desktop\app\backend\env\Scripts\python.exe
cachedir: .pytest_cache
rootdir: C:\Users\Dell\OneDrive\Desktop\app\backend\desidhar-back
configfile: pytest.ini
plugins: anyio-4.16.0, asyncio-1.5.0
asyncio: mode=Mode.AUTO, debug=False, asyncio_default_fixture_loop_scope=function, asyncio_default_test_loop_scope=function
collecting ... collected 38 items

tests/test_address_schema.py::AddressUpdateTests::test_blank_required_fields_are_rejected PASSED [  2%]
tests/test_address_schema.py::AddressUpdateTests::test_nullable_fields_can_be_cleared PASSED [  5%]
tests/test_address_schema.py::AddressUpdateTests::test_omitted_fields_are_not_changed PASSED [  7%]
tests/test_address_schema.py::AddressUpdateTests::test_patch_values_are_trimmed PASSED [ 10%]
tests/test_address_schema.py::AddressUpdateTests::test_required_fields_reject_explicit_null PASSED [ 13%]
tests/test_api_regression.py::test_categories_api PASSED                 [ 15%]
tests/test_api_regression.py::test_products_api PASSED                   [ 18%]
tests/test_api_regression.py::test_payment_methods_api PASSED            [ 21%]
tests/test_api_regression.py::test_pincodes_api PASSED                   [ 23%]
tests/test_api_regression.py::test_addresses_api_flow PASSED             [ 26%]
tests/test_api_regression.py::test_cart_validate_api PASSED              [ 28%]
tests/test_database_migrations.py::test_single_alembic_head PASSED       [ 31%]
tests/test_database_migrations.py::test_database_is_at_head PASSED       [ 34%]
tests/test_database_migrations.py::test_schema_matches_orm_models PASSED [ 36%]
tests/test_database_migrations.py::test_product_check_constraints_exist PASSED [ 39%]
tests/test_otp_auth_integration.py::test_new_customer_otp_request_endpoint PASSED [ 42%]
tests/test_otp_auth_integration.py::test_otp_request_rate_limiting PASSED [ 44%]
tests/test_otp_auth_integration.py::test_otp_resend_cooldown PASSED      [ 47%]
tests/test_otp_auth_integration.py::test_new_customer_otp_login PASSED   [ 50%]
tests/test_otp_auth_integration.py::test_existing_customer_otp_login PASSED [ 52%]
tests/test_otp_auth_integration.py::test_invalid_otp_increments_attempts PASSED [ 55%]
tests/test_otp_auth_integration.py::test_brute_force_protection_max_attempts PASSED [ 57%]
tests/test_otp_auth_integration.py::test_expired_otp_rejected PASSED     [ 60%]
tests/test_otp_auth_integration.py::test_reused_otp_rejected PASSED      [ 63%]
tests/test_otp_auth_integration.py::test_duplicate_customer_prevention PASSED [ 65%]
tests/test_otp_auth_integration.py::test_concurrent_otp_verification PASSED [ 68%]
tests/test_otp_auth_integration.py::test_inactive_customer_handling PASSED [ 71%]
tests/test_otp_auth_integration.py::test_admin_cannot_login_via_customer_otp PASSED [ 73%]
tests/test_otp_auth_integration.py::test_token_generation_and_refresh PASSED [ 76%]
tests/test_otp_auth_integration.py::test_database_rollback_on_failed_operation PASSED [ 78%]
tests/test_pricing.py::test_discount_allocation PASSED                   [ 81%]
tests/test_pricing.py::test_discount_allocation_edge_cases PASSED        [ 84%]
tests/test_pricing.py::test_tax_computation PASSED                       [ 86%]
tests/test_profile.py::ProfileInputTests::test_identity_and_privilege_fields_cannot_be_updated PASSED [ 89%]
tests/test_profile.py::ProfileInputTests::test_optional_profile_fields_can_be_cleared PASSED [ 92%]
tests/test_profile.py::ProfileInputTests::test_partial_updates_preserve_unsupplied_fields PASSED [ 94%]
tests/test_profile.py::ProfileInputTests::test_profile_fields_are_trimmed PASSED [ 97%]
tests/test_profile.py::ProfileInputTests::test_rejects_invalid_profile_fields PASSED [100%]

=================== 38 passed, 23 subtests passed in 47.74s ===================
```

Also verified against live server with `python -m scripts.test_account`:
```text
PASS: profile updates commit to PostgreSQL, reload correctly, and reject invalid/privileged changes
PASS: addresses persist, optional fields clear, validation and customer ownership hold
PASS: default selection, default promotion and soft deletion persist
Test fixtures removed
```

---

## 7. Remaining Issues / Operational Notes

1. **SMTP Delivery:** The application `.env` contains Gmail SMTP credentials. In production environments where Gmail SMTP blocks or throttles outbound mass mail, an enterprise transactional email provider (such as Amazon SES, Postmark, or SendGrid) is recommended.
2. **Razorpay Live Keys:** Razorpay is operating with `PAYMENT_PROVIDER=mock` as configured in `.env`. When transitioning to live transactions, add `RAZORPAY_KEY_ID` and `RAZORPAY_KEY_SECRET`.

---

## 8. Exact Windows PowerShell Commands to Start Application

To start the DesiDhar backend server on Windows:

```powershell
# 1. Navigate to the backend directory
cd c:\Users\Dell\OneDrive\Desktop\app\backend\desidhar-back

# 2. Verify database migration status is up to date
..\env\Scripts\python.exe -m alembic upgrade head

# 3. Start the FastAPI Uvicorn server
..\env\Scripts\python.exe -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

To run the full test suite at any time:
```powershell
cd c:\Users\Dell\OneDrive\Desktop\app\backend\desidhar-back
..\env\Scripts\python.exe -m pytest -v
```
