import os
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from app.core.config import get_settings
from app.core.rate_limit import limiter
from app.api import (
    auth, admin, me, categories, products, admin_categories, admin_products,
    delivery, admin_pincodes, admin_pincodes_bulk, admin_product_delivery,
    addresses, cart, checkout, admin_coupons,
    orders, admin_orders, payments, payment_methods, admin_payment_methods,
    contact,
)

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield


app = FastAPI(title="DesiDhar Auth", lifespan=lifespan)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

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
        content=jsonable_encoder({"message": "Validation failed", "errors": errors, "detail": exc.errors()}),
    )


app.include_router(auth.router)
app.include_router(auth.auth_router)
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
app.include_router(contact.router)

# Mount static files for product images and media
static_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "static"))
os.makedirs(os.path.join(static_dir, "products"), exist_ok=True)
app.mount("/static", StaticFiles(directory=static_dir), name="static")


@app.get("/health")
async def health():
    return {"status": "ok"}
