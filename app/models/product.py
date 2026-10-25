import enum
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from sqlalchemy import (
    String, Boolean, Integer, Numeric, DateTime, Text,
    Enum, ForeignKey, CheckConstraint, Index,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.core.db import Base
from app.models.delivery_mode import DeliveryMode


class UnitEnum(str, enum.Enum):
    kg = "kg"
    g = "g"
    litre = "litre"
    ml = "ml"
    piece = "piece"
    pack = "pack"


class Product(Base):
    __tablename__ = "products"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    category_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("categories.id", ondelete="RESTRICT"), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    slug: Mapped[str] = mapped_column(String(220), unique=True, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    price_paise: Mapped[int] = mapped_column(Integer, nullable=False)
    mrp_paise: Mapped[int] = mapped_column(Integer, nullable=False)
    unit: Mapped[UnitEnum] = mapped_column(Enum(UnitEnum, native_enum=False), nullable=False)
    pack_size: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    stock_qty: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    shelf_life_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    is_veg: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    delivery_mode: Mapped[DeliveryMode] = mapped_column(Enum(DeliveryMode, native_enum=False), default=DeliveryMode.all, server_default="all", nullable=False)
    cost_price_paise: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    gst_rate_percent: Mapped[Decimal] = mapped_column(Numeric(5, 2), default=Decimal("0.00"), server_default="0.00", nullable=False)
    max_qty_per_order: Mapped[int] = mapped_column(Integer, default=10, server_default="10", nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)

    category = relationship("Category", lazy="selectin")
    images = relationship("ProductImage", lazy="selectin", order_by="ProductImage.sort_order", cascade="all, delete-orphan")

    __table_args__ = (
        CheckConstraint("price_paise >= 0", name="ck_price_paise_non_negative"),
        CheckConstraint("mrp_paise >= 0", name="ck_mrp_paise_non_negative"),
        CheckConstraint("price_paise <= mrp_paise", name="ck_price_lte_mrp"),
        CheckConstraint("stock_qty >= 0", name="ck_stock_qty_non_negative"),
        CheckConstraint("cost_price_paise >= 0", name="ck_cost_price_paise_non_negative"),
        CheckConstraint("gst_rate_percent >= 0 AND gst_rate_percent <= 100", name="ck_gst_rate_percent_range"),
        CheckConstraint("max_qty_per_order > 0", name="ck_max_qty_per_order_positive"),
        Index("ix_products_category_id", "category_id"),
        Index("ix_products_active_created", "is_active", "created_at"),
    )

