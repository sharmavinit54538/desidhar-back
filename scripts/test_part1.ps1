# scripts/test_part1.ps1 - Automated verification of Part 1

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

Write-Host "================ 1. ADDRESS CREATION & ISOLATION ================"
# Create Address 1 for C1
$addr1_json = curl.exe -s -X POST -H "Authorization: Bearer $c1_token" -H "Content-Type: application/json" -d "{\`"full_name\`": \`"Vinit Sharma\`", \`"phone\`": \`"9876543210\`", \`"line1\`": \`"123 Street\`", \`"city\`": \`"Hyderabad\`", \`"state\`": \`"Telangana\`", \`"pincode\`": \`"500001\`", \`"is_default\`": true}" "http://127.0.0.1:8000/addresses"
Write-Host "Created Address 1:" $addr1_json
$addr1_id = ($addr1_json | ConvertFrom-Json).id

# Create Address 2 for C1
$addr2_json = curl.exe -s -X POST -H "Authorization: Bearer $c1_token" -H "Content-Type: application/json" -d "{\`"full_name\`": \`"Vinit Bangalore\`", \`"phone\`": \`"9876543210\`", \`"line1\`": \`"456 MG Road\`", \`"city\`": \`"Bengaluru\`", \`"state\`": \`"Karnataka\`", \`"pincode\`": \`"560001\`", \`"is_default\`": false}" "http://127.0.0.1:8000/addresses"
Write-Host "Created Address 2:" $addr2_json
$addr2_id = ($addr2_json | ConvertFrom-Json).id

# Set Address 2 as default
$addr2_def = curl.exe -s -X POST -H "Authorization: Bearer $c1_token" "http://127.0.0.1:8000/addresses/$addr2_id/default"
Write-Host "Made Address 2 Default:" ($addr2_def | ConvertFrom-Json).is_default

# Customer 2 attempts to access Customer 1's address -> Expect 404
Write-Host "`nCustomer 2 accessing Customer 1's address (Expect 404):"
curl.exe -s -w "`nHTTP_STATUS: %{http_code}`n" -X PATCH -H "Authorization: Bearer $c2_token" -H "Content-Type: application/json" -d "{\`"line1\`": \`"Hacked\`"}" "http://127.0.0.1:8000/addresses/$addr1_id"

Write-Host "`n================ 2. CART OPERATIONS & VALIDATION ================"
# Clear cart first
curl.exe -s -X DELETE -H "Authorization: Bearer $c1_token" "http://127.0.0.1:8000/cart"

# Add Milk (qty 2)
Write-Host "Adding 2 Milk:"
curl.exe -s -X PUT -H "Authorization: Bearer $c1_token" -H "Content-Type: application/json" -d "{\`"quantity\`": 2}" "http://127.0.0.1:8000/cart/items/$product_milk"
Write-Host "`n"

# Add Ghee (qty 1)
Write-Host "Adding 1 Ghee:"
curl.exe -s -X PUT -H "Authorization: Bearer $c1_token" -H "Content-Type: application/json" -d "{\`"quantity\`": 1}" "http://127.0.0.1:8000/cart/items/$product_ghee"
Write-Host "`n"

# Reject quantity exceeding max_qty_per_order (e.g. 99)
Write-Host "Requesting quantity exceeding limit (99):"
curl.exe -s -w "`nHTTP_STATUS: %{http_code}`n" -X PUT -H "Authorization: Bearer $c1_token" -H "Content-Type: application/json" -d "{\`"quantity\`": 99}" "http://127.0.0.1:8000/cart/items/$product_milk"
Write-Host "`n"

# View Cart
Write-Host "Viewing Cart:"
curl.exe -s -H "Authorization: Bearer $c1_token" "http://127.0.0.1:8000/cart"
Write-Host "`n"

Write-Host "================ 3. CHECKOUT PREVIEW WITH & WITHOUT COUPON ================"
# Preview without coupon (address 1 - 500001, where both Milk and Ghee are deliverable)
Write-Host "Preview at 500001 without coupon:"
curl.exe -s -X POST -H "Authorization: Bearer $c1_token" -H "Content-Type: application/json" -d "{\`"address_id\`": \`"$addr1_id\`", \`"payment_method\`": \`"cod\`"}" "http://127.0.0.1:8000/checkout/preview"
Write-Host "`n"

# Preview with valid WELCOME10 coupon
Write-Host "Preview at 500001 with coupon WELCOME10:"
curl.exe -s -X POST -H "Authorization: Bearer $c1_token" -H "Content-Type: application/json" -d "{\`"address_id\`": \`"$addr1_id\`", \`"coupon_code\`": \`"WELCOME10\`", \`"payment_method\`": \`"cod\`"}" "http://127.0.0.1:8000/checkout/preview"
Write-Host "`n"

# Preview with EXPIRED20 coupon (Expect error in blocking_reasons, can_checkout=false)
Write-Host "Preview with EXPIRED20 coupon (Expect blocking reason):"
curl.exe -s -X POST -H "Authorization: Bearer $c1_token" -H "Content-Type: application/json" -d "{\`"address_id\`": \`"$addr1_id\`", \`"coupon_code\`": \`"EXPIRED20\`"}" "http://127.0.0.1:8000/checkout/preview"
Write-Host "`n"

# Preview at address 2 (560001, where Full Cream Milk was set to selected 500001/500034) -> Expect deliverability block!
Write-Host "Preview at 560001 (Expect undeliverable item block):"
curl.exe -s -X POST -H "Authorization: Bearer $c1_token" -H "Content-Type: application/json" -d "{\`"address_id\`": \`"$addr2_id\`"}" "http://127.0.0.1:8000/checkout/preview"
Write-Host "`n"

Write-Host "================ 4. ADMIN COUPON SECURITY ================"
# Customer gets 403 on /admin/coupons
Write-Host "Customer accessing /admin/coupons (Expect 403):"
curl.exe -s -w "`nHTTP_STATUS: %{http_code}`n" -H "Authorization: Bearer $c1_token" "http://127.0.0.1:8000/admin/coupons"

# Admin lists coupons
Write-Host "Admin accessing /admin/coupons (Expect 200):"
curl.exe -s -H "Authorization: Bearer $admin_token" "http://127.0.0.1:8000/admin/coupons"
Write-Host "`n"
