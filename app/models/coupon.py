import enum
import uuid
from datetime import datetime, timezone
from sqlalchemy import String, Boolean, Integer, DateTime, Enum, CheckConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from app.core.db import Base


class CouponType(str, enum.Enum):
    percent = "percent"
    flat = "flat"


class Coupon(Base):
    __tablename__ = "coupons"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    code: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, index=True)
    description: Mapped[str | None] = mapped_column(String(255), nullable=True)
    type: Mapped[CouponType] = mapped_column(Enum(CouponType, native_enum=False), nullable=False)
    value: Mapped[int] = mapped_column(Integer, nullable=False)
    max_discount_paise: Mapped[int | None] = mapped_column(Integer, nullable=True)
    min_order_paise: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    usage_limit_total: Mapped[int | None] = mapped_column(Integer, nullable=True)
    usage_limit_per_user: Mapped[int | None] = mapped_column(Integer, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)

    __table_args__ = (
        CheckConstraint("value > 0", name="ck_coupons_value_positive"),
        CheckConstraint("min_order_paise >= 0", name="ck_coupons_min_order_non_negative"),
        CheckConstraint("max_discount_paise IS NULL OR max_discount_paise >= 0", name="ck_coupons_max_discount_non_negative"),
        CheckConstraint("ends_at >= starts_at", name="ck_coupons_valid_date_range"),
    )

