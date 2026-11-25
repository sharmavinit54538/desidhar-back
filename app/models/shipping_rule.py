import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Integer, JSON, String, CheckConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class ShippingRule(Base):
    """Admin-managed delivery promise for a destination; narrow matches win."""
    __tablename__ = "shipping_rules"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    pincode: Mapped[str | None] = mapped_column(String(6), nullable=True, index=True)
    city: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    state: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    shipping_zone: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    standard_days: Mapped[int] = mapped_column(Integer, default=5, server_default="5", nullable=False)
    express_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    working_weekdays: Mapped[list] = mapped_column(JSON, default=lambda: [0, 1, 2, 3, 4, 5], nullable=False)
    holidays: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)

    __table_args__ = (
        CheckConstraint("standard_days >= 0", name="ck_shipping_rule_standard_days"),
        CheckConstraint("express_days IS NULL OR express_days >= 0", name="ck_shipping_rule_express_days"),
    )
