# DesiDhar E-Commerce Payment Integration Report

## Overview
This document describes the Razorpay payment gateway integration, replacing the mock provider for production use.

## Architecture

### Payment Provider Abstraction
```
PaymentProvider (ABC)
├── MockPaymentProvider (dev/test only)
└── RazorpayPaymentProvider (production)
```

### Configuration
```env
PAYMENT_PROVIDER=razorpay
RAZORPAY_KEY_ID=rzp_live_xxx
RAZORPAY_KEY_SECRET=xxx
RAZORPAY_WEBHOOK_SECRET=xxx
```

### Startup Validation
- Production mode + mock provider → RuntimeError
- Razorpay selected but credentials missing → RuntimeError
- Dev mode + mock provider → Allowed

## Implementation Details

### 1. Order Creation (`POST /orders`)
- Creates order with `payment_pending` status for online payments
- Returns `PlaceOrderResponse` with `payment_url` for redirect
- Idempotency key prevents duplicate orders

### 2. Payment Initiation (`POST /orders/{id}/pay`)
- Validates order ownership
- Calls provider.create_order() with amount and receipt
- Stores provider_order_id in Payment record
- Returns provider order details to frontend

### 3. Frontend Payment Flow
1. User redirected to Razorpay checkout (via payment_url)
2. Razorpay processes payment
3. Razorpay redirects back to frontend with payment params
4. Frontend calls `POST /payments/verify` with:
   - razorpay_order_id
   - razorpay_payment_id
   - razorpay_signature

### 4. Payment Verification (`POST /payments/verify`)
- Verifies Razorpay signature (HMAC-SHA256)
- **Validates order ownership** (order.user_id == current_user.id)
- Calls confirm_payment_success()
- Updates Payment status to PAID
- Updates Order status to PLACED
- Creates OrderStatusHistory entry

### 5. Webhook Processing (`POST /payments/webhook`)
- Verifies webhook signature (HMAC-SHA256)
- Handles `payment.captured` events
- **Idempotent**: Checks if payment already PAID before processing
- Updates Payment and Order status
- Returns 200 to acknowledge receipt

### 6. Refund Processing (`POST /admin/orders/{id}/refunds`)
- Validates refund amount ≤ paid total
- For online payments: Calls provider.refund_payment()
- Updates Payment.raw_payload with refund details
- Creates Refund record
- Updates Order.payment_status (REFUNDED/PARTIALLY_REFUNDED)
- Optional restock via stock service

## Security Features

### Signature Verification
```python
# Payment verification (frontend callback)
generated = HMAC-SHA256(key_secret, f"{order_id}|{payment_id}")
compare_digest(generated, received_signature)

# Webhook verification
generated = HMAC-SHA256(webhook_secret, json.dumps(payload, separators=(",", ":")))
compare_digest(generated, x_razorpay_signature_header)
```

### Ownership Validation
- `/payments/verify` checks `Order.user_id == current_user.id`
- Prevents payment verification for other users' orders

### Idempotency
- Order creation: `idempotency_key` header (unique per user)
- Webhook processing: Checks `Payment.status == PAID` before processing
- Refund: Validates total refunded ≤ order total

### Amount Validation
- All amounts in integer paise (no floating point)
- Refund amount validated against order total
- Payment amount matches order total at initiation

## Error Handling

| Scenario | Response |
|----------|----------|
| Invalid signature | 400 "Payment verification failed" |
| Order not found | 404 "Order not found" |
| Order not owned by user | 400 "Payment verification failed" |
| Payment already processed | 200 (idempotent success) |
| Webhook signature invalid | 400 "Invalid webhook signature" |
| Refund exceeds paid amount | 422 "Cannot exceed paid total" |
| Gateway refund fails | 422 "Payment gateway refund failed" |

## Testing Checklist

### Sandbox Testing
- [ ] Successful payment flow (COD and online)
- [ ] Failed payment (insufficient funds, cancelled)
- [ ] Payment verification with valid signature
- [ ] Payment verification with invalid signature
- [ ] Webhook processing (payment.captured)
- [ ] Duplicate webhook handling
- [ ] Full refund (online payment)
- [ ] Partial refund (online payment)
- [ ] Refund with restock
- [ ] COD order delivered → payment marked paid
- [ ] Expired payment order cancellation

### Production Readiness
- [ ] Live Razorpay credentials configured
- [ ] Webhook URL registered in Razorpay dashboard
- [ ] Webhook secret configured
- [ ] PAYMENT_PROVIDER=razorpay in production
- [ ] Rate limiting on payment endpoints
- [ ] Monitoring/alerting on payment failures

## Integration Points

### Frontend
- `accountApi.placeOrder()` returns payment_url for online payments
- Frontend redirects to payment_url
- Frontend calls `/payments/verify` on return
- `validatePlacedOrder()` validates response format

### Admin
- Admin can view payment details in order view
- Admin can process refunds via `/admin/orders/{id}/refunds`
- Admin can cancel expired unpaid orders

### Inventory
- Stock reserved at order creation
- Stock released on payment timeout/cancellation
- Stock restored on refund (if restock=true)

## Monitoring Recommendations
- Track payment success/failure rates
- Monitor webhook delivery failures
- Alert on refund failures
- Track order payment_pending → placed conversion time
- Monitor expired order cancellation rate