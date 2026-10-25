import uuid
from datetime import datetime, timezone
from sqlalchemy import String, Boolean, Integer, DateTime, CheckConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from app.core.db import Base


class Pincode(Base):
    __tablename__ = "pincodes"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    pincode: Mapped[str] = mapped_column(String(6), unique=True, nullable=False, index=True)
    area_name: Mapped[str] = mapped_column(String(200), nullable=False)
    city: Mapped[str] = mapped_column(String(100), nullable=False)
    state: Mapped[str] = mapped_column(String(100), nullable=False)
    is_serviceable: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    delivery_fee_paise: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    free_delivery_above_paise: Mapped[int | None] = mapped_column(Integer, nullable=True)
    min_order_paise: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    cod_available: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    eta_hours: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)

    __table_args__ = (
        CheckConstraint("pincode ~ '^[1-9][0-9]{5}$'", name="ck_pincodes_pincode_format"),
        CheckConstraint("delivery_fee_paise >= 0", name="ck_pincodes_delivery_fee_ge_zero"),
        CheckConstraint("min_order_paise >= 0", name="ck_pincodes_min_order_ge_zero"),
        CheckConstraint("free_delivery_above_paise IS NULL OR free_delivery_above_paise >= 0", name="ck_pincodes_free_delivery_ge_zero"),
        CheckConstraint("eta_hours IS NULL OR eta_hours >= 0", name="ck_pincodes_eta_hours_ge_zero"),
    )

