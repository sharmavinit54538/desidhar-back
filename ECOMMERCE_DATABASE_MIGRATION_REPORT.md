# DesiDhar E-Commerce Database Migration Report

## Migration History

### Applied Migrations (Current Head: c7a10243e8d1)
| Revision | Description | Date | Status |
|----------|-------------|------|--------|
| 3a5efb8c6014 | init auth tables (users, otp_codes) | 2026-10-25 | ✅ Applied |
| 5bef97671fee | products (categories, products, product_images) | 2026-10-25 | ✅ Applied |
| 119232584104 | delivery_pincodes (pincodes, product_pincodes, delivery_mode) | 2026-10-25 | ✅ Applied |
| b5d58428f1bc | part1_addresses_cart_coupons (addresses, carts, cart_items, coupons, coupon_redemptions) | 2026-10-25 | ✅ Applied |
| 507c90bd6952 | part2_orders_payments_refunds (orders, order_items, order_status_history, payments, refunds) | 2026-10-25 | ✅ Applied |
| c7a10243e8d1 | payment_methods (payment_methods table + seed data) | 2026-10-26 | ✅ Applied |

### Migration Verification
```bash
alembic current
# Output: c7a10243e8d1 (head)

alembic history
# Shows linear history from base to head with no branches

alembic heads
# Single head: c7a10243e8d1
```

## Schema Summary

### Core Tables
| Table | Purpose | Key Constraints |
|-------|---------|-----------------|
| users | Customers & admins | Unique email/username, role check constraint |
| otp_codes | Email OTP verification | Index on email+created_at, consumed_at for invalidation |
| categories | Product categories | Unique name, slug |
| products | Product catalog | Price ≤ MRP, stock ≥ 0, unique slug |
| product_images | Product images | FK to products, cascade delete |
| addresses | Customer addresses | Phone/pincode format validation, unique default per user |
| carts | Shopping carts | One per user |
| cart_items | Cart line items | Unique (cart, product), quantity > 0 |
| coupons | Discount coupons | Valid date range, value > 0 |
| coupon_redemptions | Coupon usage tracking | Unique per order |

### Order & Payment Tables
| Table | Purpose | Key Constraints |
|-------|---------|-----------------|
| orders | Customer orders | Total = subtotal - discount + delivery_fee, unique idempotency per user |
| order_items | Order line items | Snapshot of product data at purchase time |
| order_status_history | Status audit trail | FK to orders, changed_by references users |
| payments | Payment records | FK to orders, provider_order_id for reconciliation |
| refunds | Refund records | Amount > 0, links to order and optionally order_item |

### Delivery Tables
| Table | Purpose | Key Constraints |
|-------|---------|-----------------|
| pincodes | Delivery areas | Valid pincode format, fee ≥ 0 |
| product_pincodes | Product-specific delivery | Composite PK (product, pincode) |

### Payment Methods Table
| Table | Purpose | Seed Data |
|-------|---------|-----------|
| payment_methods | Available payment options | COD, UPI, Card, Net Banking |

## Data Integrity Features

### Foreign Keys
- All relationships use explicit FK constraints with appropriate CASCADE/RESTRICT/SET NULL
- `orders.user_id` → `users.id` (RESTRICT)
- `order_items.order_id` → `orders.id` (CASCADE)
- `order_items.product_id` → `products.id` (RESTRICT)
- `payments.order_id` → `orders.id` (CASCADE)
- `refunds.order_id` → `orders.id` (CASCADE)
- `addresses.user_id` → `users.id` (CASCADE)

### Check Constraints
- `products`: price_paise ≥ 0, mrp_paise ≥ 0, price_paise ≤ mrp_paise, stock_qty ≥ 0
- `orders`: total_paise = subtotal_paise - discount_paise + delivery_fee_paise
- `cart_items`: quantity > 0
- `coupons`: value > 0, ends_at ≥ starts_at
- `refunds`: amount_paise > 0
- `addresses`: phone format (10 digits starting 6-9), pincode format (6 digits, not starting with 0)

### Unique Constraints
- `users.email` (case-insensitive index)
- `users.username` (case-insensitive index)
- `products.slug`
- `categories.name`
- `coupons.code`
- `pincodes.pincode`
- `payment_methods.code`
- `cart_items`: (cart_id, product_id)
- `orders`: (user_id, idempotency_key)
- `coupon_redemptions`: order_id

### Indexes
- `products`: category_id, (is_active, created_at)
- `orders`: order_number, shipping_pincode, (status, placed_at), (user_id, placed_at)
- `payments`: order_id
- `refunds`: (order_id, issued_at)
- `otp_codes`: (email, created_at DESC)
- `addresses`: user_id (where deleted_at IS NULL), user_id (where is_default AND deleted_at IS NULL)

## Migration Safety

### Production Deployment
1. Run `alembic upgrade head` before deploying new code
2. Migrations are additive only (no destructive changes in history)
3. No data migration required for current changes
4. Backward compatible with existing API versions

### Rollback Plan
- Each migration has `downgrade()` function
- Test rollback in staging before production
- Backup database before migration

### New Migration Process
```bash
# Create new migration
alembic revision --autogenerate -m "description"

# Review generated SQL
alembic upgrade head  # Test apply
alembic downgrade -1  # Test rollback
```

## Configuration Requirements

### Environment Variables
```env
DATABASE_URL=postgresql+asyncpg://user:pass@host:5432/desidhar
# For alembic (sync driver):
# postgresql+psycopg2://user:pass@host:5432/desidhar
```

### Extensions Required
- `pg_trgm` for full-text search (optional, commented in migration)
- `uuid-ossp` (built-in for UUID generation)

## Testing Performed
- ✅ Clean database migration from base
- ✅ Existing database migration to head
- ✅ Schema matches SQLAlchemy models
- ✅ All constraints enforce correctly
- ✅ Foreign key cascades work as expected
- ✅ Check constraints prevent invalid data