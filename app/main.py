from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from app.core.config import get_settings
from app.api import (
    auth, admin, me, categories, products, admin_categories, admin_products,
    delivery, admin_pincodes, admin_pincodes_bulk, admin_product_delivery,
    addresses, cart, checkout, admin_coupons,
    orders, admin_orders, payments, payment_methods, admin_payment_methods,
)

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield


app = FastAPI(title="DesiDhar Auth", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    errors = []
    for err in exc.errors():
        loc = err.get("loc", [])
        clean_loc = [str(l) for l in loc if l not in ("body",)]
        field = ".".join(clean_loc) if clean_loc else "body"
        msg = err.get("msg", "Validation error")
        errors.append({"field": field, "message": msg})
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={"message": "Validation failed", "errors": errors, "detail": exc.errors()},
    )


app.include_router(auth.router)
app.include_router(admin.router)
app.include_router(me.router)
app.include_router(categories.router)
app.include_router(products.router)
app.include_router(admin_categories.router)
app.include_router(admin_products.router)
app.include_router(delivery.router)
app.include_router(admin_pincodes_bulk.router)
app.include_router(admin_pincodes.router)
app.include_router(admin_product_delivery.router)
app.include_router(addresses.router)
app.include_router(cart.router)
app.include_router(checkout.router)
app.include_router(admin_coupons.router)
app.include_router(orders.router)
app.include_router(admin_orders.router)
app.include_router(payments.router)
app.include_router(payment_methods.router)
app.include_router(admin_payment_methods.router)



@app.get("/health")
async def health():
    return {"status": "ok"}