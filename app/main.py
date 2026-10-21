import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.exceptions import RequestValidationError
from sqlalchemy.exc import SQLAlchemyError
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from app.core.config import settings
from app.core.database import engine, AsyncSessionLocal
from app.core.redis import init_redis, close_redis, get_redis
from app.core.rate_limit import limiter
from app.core.exceptions import (
    AppException,
    app_exception_handler,
    validation_exception_handler,
    sqlalchemy_exception_handler,
    general_exception_handler,
)
from app.api.v1.api_router import api_router
from app.models.base import Base
from app.db.seed import seed_initial_data

# Configure structured logging
logging.basicConfig(
    level=logging.DEBUG if settings.DEBUG else logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s:%(lineno)d - %(message)s",
)
logger = logging.getLogger("desidhar.main")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Initializing DesiDhar E-Commerce Platform Backend...")

    # 1. Connect Redis
    await init_redis()

    # 2. Database schema initialization & Auto-seed default SUPER_ADMIN
    try:
        async with engine.begin() as conn:
            # Create tables if not existing (ideal for dev/testing before alembic upgrade)
            await conn.run_sync(Base.metadata.create_all)
        logger.info("Database tables verified.")

        # Seed initial SUPER_ADMIN and catalog data
        async with AsyncSessionLocal() as session:
            await seed_initial_data(session)
        logger.info("Database seeding checked.")
    except Exception as e:
        logger.warning(f"Database bootstrap note ({e}). Continuing startup.")

    logger.info("Application startup sequence completed successfully.")
    yield

    # Cleanup sequence
    logger.info("Initiating application shutdown sequence...")
    await close_redis()
    await engine.dispose()
    logger.info("Application shutdown complete.")


app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    description="Scalable, Production-Grade Single-Vendor D2C E-Commerce Platform API",
    lifespan=lifespan,
    docs_url=f"{settings.API_V1_STR}/docs",
    redoc_url=f"{settings.API_V1_STR}/redoc",
    openapi_url=f"{settings.API_V1_STR}/openapi.json",
)

# ------------------ RATE LIMITER SETUP ------------------
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# ------------------ CORS MIDDLEWARE ------------------
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.BACKEND_CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ------------------ GLOBAL RFC 7807 EXCEPTION HANDLERS ------------------
app.add_exception_handler(AppException, app_exception_handler)
app.add_exception_handler(RequestValidationError, validation_exception_handler)
app.add_exception_handler(SQLAlchemyError, sqlalchemy_exception_handler)
app.add_exception_handler(Exception, general_exception_handler)

# ------------------ MOUNT API ROUTERS ------------------
app.include_router(api_router, prefix=settings.API_V1_STR)


@app.get(
    "/health",
    tags=["System"],
    status_code=status.HTTP_200_OK,
    summary="Health check endpoint",
)
async def health_check():
    redis_active = get_redis() is not None
    return {
        "status": "healthy",
        "app_name": settings.PROJECT_NAME,
        "version": settings.VERSION,
        "environment": settings.ENVIRONMENT,
        "redis_connected": redis_active,
    }
