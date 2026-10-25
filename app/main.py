from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.core.config import get_settings
from app.api import (
    auth, admin, me, categories, products, admin_categories, admin_products,
    delivery, admin_pincodes, admin_pincodes_bulk, admin_product_delivery,
    addresses, cart, checkout, admin_coupons,
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


@app.get("/health")
async def health():
    return {"status": "ok"}