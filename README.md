# DesiDhar - Single-Vendor D2C Brand Store Backend

A scalable, production-grade, 100% asynchronous E-Commerce Backend built with **FastAPI**, **PostgreSQL (SQLAlchemy 2.0 Async)**, **Redis**, and **Pydantic v2**.

---

## 🛠 Tech Stack & Architecture

- **Runtime & Web Framework**: Python 3.11+ / 3.14 with FastAPI (100% Async)
- **Database & ORM**: PostgreSQL with SQLAlchemy 2.0 (`AsyncSession`, declarative `mapped_column`, `with_for_update()`) and Alembic for migrations
- **Caching & Rate Limiting**: Redis (`redis-py` async) for sessions, guest cart caching, and SlowAPI rate limiting
- **Data Validation & Settings**: Pydantic v2 & `pydantic-settings`
- **Security & Password Hashing**: `pwdlib` (Argon2) with `bcrypt` fallback (strictly avoids deprecated `passlib`), PyJWT, HTTP-Only secure cookies
- **Payment Gateway Architecture**: Razorpay & Stripe webhook-driven idempotency architecture with HMAC verification
- **Error Handling**: RFC 7807 centralized problem details response format

---

## 📁 Project Directory Layout

```
desidhar-back/
├── app/
│   ├── main.py                  # FastAPI entrypoint, lifespan startup/shutdown, CORS, SlowAPI, RFC 7807 handlers
│   ├── core/
│   │   ├── config.py            # BaseSettings with .env validation & defaults
│   │   ├── database.py          # SQLAlchemy 2.0 AsyncEngine, async_sessionmaker, get_db generator
│   │   ├── dependencies.py      # get_current_user, RoleChecker, PermissionChecker, guest session extractor
│   │   ├── exceptions.py        # Centralized RFC 7807 AppException hierarchy and global handlers
│   │   ├── rate_limit.py        # SlowAPI Limiter configured with Redis backend
│   │   ├── redis.py             # Redis async connection manager & guest cart cache
│   │   └── security.py          # Argon2 / bcrypt password hashing, token creation & decoding, token hashing
│   ├── models/
│   │   ├── base.py              # Base DeclarativeBase, UUIDPrimaryKeyMixin, TimestampMixin
│   │   ├── user.py              # User, UserSession, UserRole, UserStatus
│   │   ├── catalog.py           # Category, Product, ProductImage, ProductStatus
│   │   ├── cart.py              # Cart, CartItem with unique constraint
│   │   ├── order.py             # Order, OrderItem with snapshot pricing and SKU
│   │   ├── payment.py           # PaymentTransaction, IdempotencyKey
│   │   └── __init__.py          # Exports all models for Alembic autogeneration
│   ├── schemas/
│   │   ├── auth.py              # UserRegister, StaffCreate, Login, Token, Session responses
│   │   ├── catalog.py           # Category and Product create/update/filter schemas
│   │   ├── cart.py              # CartItem and Cart responses, merge request schema
│   │   ├── order.py             # Order checkout, OrderItem snapshot, status updates
│   │   ├── payment.py           # Gateway initialization and verification schemas
│   │   └── common.py            # RFC 7807 error schema and PaginatedResponse
│   ├── services/
│   │   ├── auth_service.py      # Registration, login, token rotation, session killing on reuse detection
│   │   ├── catalog_service.py   # Public catalog filtering, admin CRUD, safe soft-archive, hard-delete protection
│   │   ├── cart_service.py      # Redis guest cart, DB authenticated cart, auto-merge logic, dynamic stock checks
│   │   ├── order_service.py     # Row-level locking (SELECT FOR UPDATE) checkout, cancellation, inventory rollback
│   │   ├── payment_service.py   # Razorpay/Stripe order init, HMAC verification, idempotency locks
│   │   └── notification_service.py # Transactional notification dispatcher (email, SMS, receipts)
│   ├── api/
│   │   └── v1/
│   │       ├── api_router.py    # Master router
│   │       ├── auth.py          # Authentication, refresh, logout, staff management
│   │       ├── products.py      # Public catalog & Admin safe delete endpoints
│   │       ├── cart.py          # Guest/User cart operations and merging
│   │       ├── orders.py        # Checkout, order listing, status progression, cancellation
│   │       └── webhooks.py      # Cryptographically verified payment webhooks
│   └── db/
│       └── seed.py              # Automatic SUPER_ADMIN initialization & catalog bootstrap
├── alembic/
│   ├── env.py                   # Async Alembic migration runner
│   ├── script.py.mako           # Migration template
│   └── versions/                # Generated migration versions
├── tests/
│   ├── test_core_and_security.py
│   ├── test_business_logic.py
│   └── test_auth_service.py
├── alembic.ini
├── requirements.txt
├── .env.example
└── README.md
```

---

## 🔐 Security & RBAC Model

### 1. Granular Roles & Permissions
- **`SUPER_ADMIN`**: Full platform control, bypasses all permission checks automatically, can create staff with customized permission sets, only role allowed to permanently delete products.
- **`STORE_MANAGER`**: Catalog & inventory management (`product:write`, `category:write`, `inventory:update`).
- **`SUPPORT_STAFF`**: Order support, refund processing, shipping status updates (`order:read`, `order:refund`, `order:update`).
- **`CUSTOMER`**: Public registration, cart management, checkout, viewing & cancelling own orders.

### 2. Token Rotation & Reuse Detection
- Short-lived Access Token (15 mins) + Long-lived Refresh Token (7 days) via HTTP-Only, Secure, SameSite='Lax' cookies.
- Refresh tokens are hashed via SHA-256 before storage in `user_sessions` (never stored in plaintext).
- **Reuse Detection Trigger**: If a previously rotated or revoked refresh token is presented, the system immediately flags a security breach, terminates **all** active sessions for that user, and raises an emergency security alert (`TOKEN_REUSE_DETECTED`).

---

## ⚡ Concurrency & Flash Sale Inventory Protection

During high-concurrency checkout:
1. Product IDs in the user's cart are **deterministically sorted** before querying.
2. The database executes **pessimistic row-level locking**:
   ```sql
   SELECT * FROM products WHERE id IN (...) ORDER BY id FOR UPDATE;
   ```
3. Checks available stock against requested quantities under the lock.
4. Atomically decrements `product.stock -= requested_quantity`.
5. If payment fails or the order is cancelled, inventory is atomically restored:
   ```sql
   SELECT * FROM products WHERE id IN (...) ORDER BY id FOR UPDATE;
   UPDATE products SET stock = stock + item.quantity WHERE id = ...;
   ```

---

## 💳 Payment Gateway & Webhook Idempotency

- Supports both **Razorpay** and **Stripe**.
- Webhook endpoints verify cryptographic signatures (HMAC-SHA256).
- An **`IdempotencyKey`** table tracks event identifiers (`event_id` / `payment_id`).
- Incoming duplicate webhooks are detected immediately and return `200 OK` (idempotent response) without re-executing state transitions or stock deductions.

---

## 🚀 Getting Started

### 1. Install Dependencies
```bash
pip install -r requirements.txt
```

### 2. Configure Environment
```bash
cp .env.example .env
# Update DATABASE_URL and REDIS_URL in .env
```

### 3. Run Migrations & Database Seeding
```bash
# Run migrations
alembic upgrade head

# Or seed initial SUPER_ADMIN and demo catalog
python -m app.db.seed
```

### 4. Start Development Server
```bash
uvicorn app.main:app --reload --port 8000
```
Interactive API documentation is accessible at:
- Swagger UI: `http://localhost:8000/api/v1/docs`
- ReDoc: `http://localhost:8000/api/v1/redoc`
- Health Check: `http://localhost:8000/health`

### 5. Running Tests
```bash
pytest tests/ -v
```