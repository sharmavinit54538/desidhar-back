# scripts/test_part2.ps1 - Complete verification of Part 2 with curl.exe

$run_id = [guid]::NewGuid().ToString().Substring(0, 8)
Write-Host "Test Run ID: $run_id"

$tokens = $(python -c "
import asyncio
from app.core.db import async_session_maker
from app.models.user import User, Role
from app.services.auth_service import get_or_create_customer
from app.core.tokens import create_admin_token, create_customer_token
from sqlalchemy import select

async def main():
    async with async_session_maker() as session:
        adm = (await session.execute(select(User).where(User.role == Role.admin))).scalar_one()
        c1 = (await session.execute(select(User).where(User.role == Role.customer))).scalars().first()
        c2 = await get_or_create_customer(session, 'customer2@example.com')
        await session.commit()
        print(f'{create_admin_token(str(adm.id))}|{create_customer_token(str(c1.id))}|{create_customer_token(str(c2.id))}')

asyncio.run(main())
").Trim().Split('|')

$admin_token = $tokens[0]
$c1_token = $tokens[1]
$c2_token = $tokens[2]

$c1_addr_id = $(python -c "
import asyncio
from app.core.db import async_session_maker
from app.models.user import User, Role
from app.models.address import Address
from sqlalchemy import select

async def main():
    async with async_session_maker() as session:
        c1 = (await session.execute(select(User).where(User.role == Role.customer))).scalars().first()
        a = (await session.execute(select(Address).where(Address.user_id == c1.id, Address.pincode == '500001', Address.deleted_at.is_(None)))).scalars().first()
        print(str(a.id))

asyncio.run(main())
").Trim()

$product_milk = $(python -c "
import asyncio
from app.core.db import async_session_maker
from app.models.product import Product
from sqlalchemy import select

async def main():
    async with async_session_maker() as session:
        p = (await session.execute(select(Product).where(Product.slug == 'full-cream-milk'))).scalar_one()
        print(str(p.id))

asyncio.run(main())
").Trim()

$product_ghee = $(python -c "
import asyncio
from app.core.db import async_session_maker
from app.models.product import Product
from sqlalchemy import select

async def main():
    async with async_session_maker() as session:
        p = (await session.execute(select(Product).where(Product.slug == 'pure-desi-ghee'))).scalar_one()
        print(str(p.id))

asyncio.run(main())
").Trim()

Write-Host "================ 1. PLACE COD ORDER & VERIFY TOTALS ================"
# Fill Cart: 2 Milk (6800x2 = 13600) + 1 Ghee (59900) = 73500 subtotal
curl.exe -s -X DELETE -H "Authorization: Bearer $c1_token" "http://127.0.0.1:8000/cart" | Out-Null
curl.exe -s -X PUT -H "Authorization: Bearer $c1_token" -H "Content-Type: application/json" -d "{\`"quantity\`": 2}" "http://127.0.0.1:8000/cart/items/$product_milk" | Out-Null
curl.exe -s -X PUT -H "Authorization: Bearer $c1_token" -H "Content-Type: application/json" -d "{\`"quantity\`": 1}" "http://127.0.0.1:8000/cart/items/$product_ghee" | Out-Null

$order1_json = curl.exe -s -X POST -H "Authorization: Bearer $c1_token" -H "Idempotency-Key: order-cod-$run_id" -H "Content-Type: application/json" -d "{\`"address_id\`": \`"$c1_addr_id\`", \`"payment_method\`": \`"cod\`", \`"coupon_code\`": \`"FLAT50\`"}" "http://127.0.0.1:8000/orders"
Write-Host "Order Placed Response:"
Write-Host $order1_json
$order1 = $order1_json | ConvertFrom-Json
$order1_id = $order1.id

Write-Host "`nConsistency check:"
Write-Host "Subtotal:" $order1.subtotal_paise "Discount:" $order1.discount_paise "Delivery Fee:" $order1.delivery_fee_paise "Total:" $order1.total_paise
$calc_total = $order1.subtotal_paise - $order1.discount_paise + $order1.delivery_fee_paise
Write-Host "Calculated Total (Subtotal - Discount + Delivery Fee):" $calc_total
$items_sum = 0
foreach ($it in $order1.items) { $items_sum += $it.line_total_paise }
Write-Host "Sum of item line totals:" $items_sum
Write-Host "Sum of items + Delivery Fee:" ($items_sum + $order1.delivery_fee_paise)

Write-Host "`n================ 2. IDEMPOTENCY KEY CHECK ================"
Write-Host "Posting again with same Idempotency-Key (order-cod-$run_id):"
$idem_json = curl.exe -s -X POST -H "Authorization: Bearer $c1_token" -H "Idempotency-Key: order-cod-$run_id" -H "Content-Type: application/json" -d "{\`"address_id\`": \`"$c1_addr_id\`", \`"payment_method\`": \`"cod\`"}" "http://127.0.0.1:8000/orders"
$idem_order = $idem_json | ConvertFrom-Json
Write-Host "Same Order Number returned:" ($idem_order.order_number -eq $order1.order_number)

Write-Host "`n================ 3. CUSTOMER CANCELLATION & STOCK RESTORATION ================"
$stock_before = $(python -c "
import asyncio
from app.core.db import async_session_maker
from app.models.product import Product
from sqlalchemy import select

async def main():
    async with async_session_maker() as session:
        p = (await session.execute(select(Product).where(Product.slug == 'full-cream-milk'))).scalar_one()
        print(p.stock_qty)

asyncio.run(main())
").Trim()
Write-Host "Milk stock before cancel:" $stock_before

Write-Host "Cancelling Order:"
curl.exe -s -X POST -H "Authorization: Bearer $c1_token" -H "Content-Type: application/json" -d "{\`"reason\`": \`"Ordered by mistake\`"}" "http://127.0.0.1:8000/orders/$order1_id/cancel"
Write-Host ""

$stock_after = $(python -c "
import asyncio
from app.core.db import async_session_maker
from app.models.product import Product
from sqlalchemy import select

async def main():
    async with async_session_maker() as session:
        p = (await session.execute(select(Product).where(Product.slug == 'full-cream-milk'))).scalar_one()
        print(p.stock_qty)

asyncio.run(main())
").Trim()
Write-Host "Milk stock after cancel (should be +2):" $stock_after

Write-Host "`n================ 4. CONCURRENT / PARALLEL ORDERS FOR LAST UNIT ================"
# Set Kaju Katli stock to exactly 1
python -c "
import asyncio
from app.core.db import async_session_maker
from app.models.product import Product
from sqlalchemy import update

async def main():
    async with async_session_maker() as session:
        await session.execute(update(Product).where(Product.slug == 'kaju-katli').values(stock_qty=1))
        await session.commit()

asyncio.run(main())
"

$kaju_id = $(python -c "
import asyncio
from app.core.db import async_session_maker
from app.models.product import Product
from sqlalchemy import select

async def main():
    async with async_session_maker() as session:
        p = (await session.execute(select(Product).where(Product.slug == 'kaju-katli'))).scalar_one()
        print(str(p.id))

asyncio.run(main())
").Trim()

# Customer 1 cart
curl.exe -s -X DELETE -H "Authorization: Bearer $c1_token" "http://127.0.0.1:8000/cart" | Out-Null
curl.exe -s -X PUT -H "Authorization: Bearer $c1_token" -H "Content-Type: application/json" -d "{\`"quantity\`": 1}" "http://127.0.0.1:8000/cart/items/$kaju_id" | Out-Null

# Customer 2 address & cart
curl.exe -s -X POST -H "Authorization: Bearer $c2_token" -H "Content-Type: application/json" -d "{\`"full_name\`": \`"Customer Two\`", \`"phone\`": \`"9876543211\`", \`"line1\`": \`"789 Street\`", \`"city\`": \`"Hyderabad\`", \`"state\`": \`"Telangana\`", \`"pincode\`": \`"500001\`", \`"is_default\`": true}" "http://127.0.0.1:8000/addresses" | Out-Null
$c2_addr_id = $(python -c "
import asyncio
from app.core.db import async_session_maker
from app.models.user import User, Role
from app.models.address import Address
from sqlalchemy import select

async def main():
    async with async_session_maker() as session:
        c2 = (await session.execute(select(User).where(User.email == 'customer2@example.com'))).scalars().first()
        a = (await session.execute(select(Address).where(Address.user_id == c2.id, Address.deleted_at.is_(None)))).scalars().first()
        print(str(a.id))

asyncio.run(main())
").Trim()

curl.exe -s -X DELETE -H "Authorization: Bearer $c2_token" "http://127.0.0.1:8000/cart" | Out-Null
curl.exe -s -X PUT -H "Authorization: Bearer $c2_token" -H "Content-Type: application/json" -d "{\`"quantity\`": 1}" "http://127.0.0.1:8000/cart/items/$kaju_id" | Out-Null

# Order 1 placed by C1
$c1_kaju = curl.exe -s -w "`nHTTP_STATUS: %{http_code}`n" -X POST -H "Authorization: Bearer $c1_token" -H "Idempotency-Key: c1-kaju-$run_id" -H "Content-Type: application/json" -d "{\`"address_id\`": \`"$c1_addr_id\`", \`"payment_method\`": \`"cod\`"}" "http://127.0.0.1:8000/orders"
Write-Host "Customer 1 result (Success expected):"
Write-Host $c1_kaju

# Order 2 placed by C2 (now stock is 0 -> should fail with 422)
$c2_kaju = curl.exe -s -w "`nHTTP_STATUS: %{http_code}`n" -X POST -H "Authorization: Bearer $c2_token" -H "Idempotency-Key: c2-kaju-$run_id" -H "Content-Type: application/json" -d "{\`"address_id\`": \`"$c2_addr_id\`", \`"payment_method\`": \`"cod\`"}" "http://127.0.0.1:8000/orders"
Write-Host "Customer 2 result (Failure expected):"
Write-Host $c2_kaju

Write-Host "`n================ 5. ADMIN TRANSITIONS & COD MARKED PAID ON DELIVERY ================"
$kaju_order_id = ($c1_kaju.Split("`n")[0] | ConvertFrom-Json).id
Write-Host "Transition to confirmed:"
curl.exe -s -X POST -H "Authorization: Bearer $admin_token" -H "Content-Type: application/json" -d "{\`"status\`": \`"confirmed\`"}" "http://127.0.0.1:8000/admin/orders/$kaju_order_id/status" | Out-Null
Write-Host "Transition to packed:"
curl.exe -s -X POST -H "Authorization: Bearer $admin_token" -H "Content-Type: application/json" -d "{\`"status\`": \`"packed\`"}" "http://127.0.0.1:8000/admin/orders/$kaju_order_id/status" | Out-Null
Write-Host "Transition to out_for_delivery:"
curl.exe -s -X POST -H "Authorization: Bearer $admin_token" -H "Content-Type: application/json" -d "{\`"status\`": \`"out_for_delivery\`"}" "http://127.0.0.1:8000/admin/orders/$kaju_order_id/status" | Out-Null
Write-Host "Transition to delivered:"
$deliv_res = curl.exe -s -X POST -H "Authorization: Bearer $admin_token" -H "Content-Type: application/json" -d "{\`"status\`": \`"delivered\`"}" "http://127.0.0.1:8000/admin/orders/$kaju_order_id/status"
$deliv_obj = $deliv_res | ConvertFrom-Json
Write-Host "Delivered Status:" $deliv_obj.status
Write-Host "Delivered At:" $deliv_obj.delivered_at
Write-Host "Payment Status (should be paid):" $deliv_obj.payment_status

Write-Host "`n================ 6. REFUND VALIDATION (LIMITS & RESTOCK) ================"
# Attempt refund larger than total paid (Expect 422)
Write-Host "Attempting refund larger than total paid (Expect 422):"
curl.exe -s -w "`nHTTP_STATUS: %{http_code}`n" -X POST -H "Authorization: Bearer $admin_token" -H "Content-Type: application/json" -d "{\`"amount_paise\`": 99999999, \`"reason\`": \`"quality\`"}" "http://127.0.0.1:8000/admin/orders/$kaju_order_id/refunds"

# Valid full refund with restock=true
Write-Host "Issuing valid refund:"
$ref_res = curl.exe -s -X POST -H "Authorization: Bearer $admin_token" -H "Content-Type: application/json" -d "{\`"amount_paise\`": $($deliv_obj.total_paise), \`"reason\`": \`"quality\`", \`"restock\`": true, \`"order_item_id\`": \`"$($deliv_obj.items[0].id)\`"}" "http://127.0.0.1:8000/admin/orders/$kaju_order_id/refunds"
Write-Host $ref_res

Write-Host "`n================ 7. DATA ISOLATION (404) & RBAC (403) ================"
# C2 tries to read C1's order -> Expect 404
Write-Host "Customer 2 reading Customer 1's order (Expect 404):"
curl.exe -s -w "`nHTTP_STATUS: %{http_code}`n" -H "Authorization: Bearer $c2_token" "http://127.0.0.1:8000/orders/$kaju_order_id"

# Customer 1 accessing /admin/orders -> Expect 403
Write-Host "Customer 1 accessing /admin/orders (Expect 403):"
curl.exe -s -w "`nHTTP_STATUS: %{http_code}`n" -H "Authorization: Bearer $c1_token" "http://127.0.0.1:8000/admin/orders"

Write-Host "`n================ 8. ONLINE ORDER & IDEMPOTENT WEBHOOK ================"
# Cart: 1 Milk
curl.exe -s -X DELETE -H "Authorization: Bearer $c1_token" "http://127.0.0.1:8000/cart" | Out-Null
curl.exe -s -X PUT -H "Authorization: Bearer $c1_token" -H "Content-Type: application/json" -d "{\`"quantity\`": 1}" "http://127.0.0.1:8000/cart/items/$product_milk" | Out-Null

$online_order = curl.exe -s -X POST -H "Authorization: Bearer $c1_token" -H "Idempotency-Key: online-ord-$run_id" -H "Content-Type: application/json" -d "{\`"address_id\`": \`"$c1_addr_id\`", \`"payment_method\`": \`"online\`"}" "http://127.0.0.1:8000/orders" | ConvertFrom-Json
Write-Host "Online Order Placed. Status (Expect payment_pending):" $online_order.status

# Initiate payment
$pay_init = curl.exe -s -X POST -H "Authorization: Bearer $c1_token" "http://127.0.0.1:8000/orders/$($online_order.id)/pay" | ConvertFrom-Json
Write-Host "Payment Initiated. Provider Order ID:" $pay_init.provider_order_id

# Webhook call 1
$sig = "mock_sig_$($pay_init.provider_order_id)"
Write-Host "Sending Webhook Call 1:"
curl.exe -s -X POST -H "X-Signature: $sig" -H "Content-Type: application/json" -d "{\`"provider_order_id\`": \`"$($pay_init.provider_order_id)\`", \`"amount_paise\`": $($pay_init.amount_paise)}" "http://127.0.0.1:8000/payments/webhook"
Write-Host ""

# Webhook call 2 (idempotent, safe to receive twice)
Write-Host "Sending Webhook Call 2 (Idempotent):"
curl.exe -s -X POST -H "X-Signature: $sig" -H "Content-Type: application/json" -d "{\`"provider_order_id\`": \`"$($pay_init.provider_order_id)\`", \`"amount_paise\`": $($pay_init.amount_paise)}" "http://127.0.0.1:8000/payments/webhook"
Write-Host "`n"

# Verify online order status is now placed
$online_order_updated = curl.exe -s -H "Authorization: Bearer $c1_token" "http://127.0.0.1:8000/orders/$($online_order.id)" | ConvertFrom-Json
Write-Host "Online Order Status after Webhook (Expect placed):" $online_order_updated.status
Write-Host "Online Order Placed At:" $online_order_updated.placed_at
