# test_curl.ps1 - Automated verification using curl.exe

$admin_token = $(python -c "
import asyncio
from app.core.db import async_session_maker
from app.models.user import User, Role
from app.core.tokens import create_admin_token
from sqlalchemy import select

async def main():
    async with async_session_maker() as session:
        adm = (await session.execute(select(User).where(User.role == Role.admin))).scalar_one()
        print(create_admin_token(str(adm.id)))

asyncio.run(main())
").Trim()

$customer_token = $(python -c "
import asyncio
from app.core.db import async_session_maker
from app.models.user import User, Role
from app.core.tokens import create_customer_token
from sqlalchemy import select

async def main():
    async with async_session_maker() as session:
        cust = (await session.execute(select(User).where(User.role == Role.customer))).scalar_one()
        print(create_customer_token(str(cust.id)))

asyncio.run(main())
").Trim()

$product_id = $(python -c "
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

$pincode_id = $(python -c "
import asyncio
from app.core.db import async_session_maker
from app.models.pincode import Pincode
from sqlalchemy import select

async def main():
    async with async_session_maker() as session:
        p = (await session.execute(select(Pincode).where(Pincode.pincode == '500001'))).scalar_one()
        print(str(p.id))

asyncio.run(main())
").Trim()

Write-Host "================ 1. SERVICEABLE PINCODE CHECK ================"
curl.exe -s "http://127.0.0.1:8000/delivery/check?pincode=500001"
Write-Host "`n"

Write-Host "================ 2. NON-SERVICEABLE PINCODE CHECK ================"
curl.exe -s "http://127.0.0.1:8000/delivery/check?pincode=500099"
Write-Host "`n"

Write-Host "================ 3. UNKNOWN PINCODE CHECK ================"
curl.exe -s "http://127.0.0.1:8000/delivery/check?pincode=999999"
Write-Host "`n"

Write-Host "================ 4. INVALID PINCODE CHECK (5 digits) ================"
curl.exe -s -w "`nHTTP_STATUS: %{http_code}`n" "http://127.0.0.1:8000/delivery/check?pincode=50000"
Write-Host ""

Write-Host "================ 5. ADMIN TOGGLE (OFF then ON) ================"
Write-Host "Toggling 500001 to is_serviceable=false:"
curl.exe -s -X PATCH -H "Authorization: Bearer $admin_token" -H "Content-Type: application/json" -d "{\`"is_serviceable\`": false}" "http://127.0.0.1:8000/admin/pincodes/$pincode_id/serviceable"
Write-Host "`nCheck deliverability after toggle OFF:"
curl.exe -s "http://127.0.0.1:8000/delivery/check?pincode=500001"
Write-Host "`nToggling 500001 back to is_serviceable=true:"
curl.exe -s -X PATCH -H "Authorization: Bearer $admin_token" -H "Content-Type: application/json" -d "{\`"is_serviceable\`": true}" "http://127.0.0.1:8000/admin/pincodes/$pincode_id/serviceable"
Write-Host "`n"

Write-Host "================ 6. BULK UPSERT WITH ONE BAD ROW ================"
curl.exe -s -X POST -H "Authorization: Bearer $admin_token" -H "Content-Type: application/json" -d "[{\`"pincode\`": \`"500001\`", \`"area_name\`": \`"Abids Central\`", \`"city\`": \`"Hyderabad\`", \`"state\`": \`"Telangana\`"}, {\`"pincode\`": \`"12345\`", \`"area_name\`": \`"Invalid\`", \`"city\`": \`"Bad\`", \`"state\`": \`"Bad\`"}]" "http://127.0.0.1:8000/admin/pincodes/bulk"
Write-Host "`n"

Write-Host "================ 7. PRODUCT SET TO 'SELECTED' WITH TWO PINCODES ================"
curl.exe -s -X PUT -H "Authorization: Bearer $admin_token" -H "Content-Type: application/json" -d "{\`"mode\`": \`"selected\`", \`"pincodes\`": [\`"500001\`", \`"500034\`"]}" "http://127.0.0.1:8000/admin/products/$product_id/delivery"
Write-Host "`nCheck deliverable at 500001 (allowed):"
curl.exe -s "http://127.0.0.1:8000/products/full-cream-milk/delivery?pincode=500001"
Write-Host "`nCheck deliverable at 560001 (not allowed):"
curl.exe -s "http://127.0.0.1:8000/products/full-cream-milk/delivery?pincode=560001"
Write-Host "`n"

Write-Host "================ 8. GET /products?pincode= FILTERING ================"
Write-Host "Filter by 500001 (should include full-cream-milk):"
$res500001 = curl.exe -s "http://127.0.0.1:8000/products?pincode=500001"
Write-Host $res500001
Write-Host "`nFilter by 560001 (should NOT include full-cream-milk):"
$res560001 = curl.exe -s "http://127.0.0.1:8000/products?pincode=560001"
Write-Host $res560001
Write-Host "`nFilter by 500099 (non-serviceable pincode):"
curl.exe -s "http://127.0.0.1:8000/products?pincode=500099"
Write-Host "`n"

Write-Host "================ 9. CUSTOMER TOKEN GETS 403 ON /admin/pincodes ================"
curl.exe -s -w "`nHTTP_STATUS: %{http_code}`n" -H "Authorization: Bearer $customer_token" "http://127.0.0.1:8000/admin/pincodes"
Write-Host ""

