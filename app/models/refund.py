import enum
import uuid
from datetime import datetime, timezone
from sqlalchemy import String, Boolean, Integer, DateTime, Enum, ForeignKey, Index, CheckConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from app.core.db import Base


class RefundReason(str, enum.Enum):
    cancelled = "cancelled"
    damaged = "damaged"
    wrong_item = "wrong_item"
    quality = "quality"
    late = "late"
    other = "other"


class Refund(Base):
    __tablename__ = "refunds"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    order_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("orders.id", ondelete="CASCADE"), nullable=False)
    order_item_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("order_items.id", ondelete="SET NULL"), nullable=True)
    amount_paise: Mapped[int] = mapped_column(Integer, nullable=False)
    reason: Mapped[RefundReason] = mapped_column(Enum(RefundReason, native_enum=False), nullable=False)
    notes: Mapped[str | None] = mapped_column(String(255), nullable=True)
    restock: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    issued_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    issued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)

    __table_args__ = (
        CheckConstraint("amount_paise > 0", name="ck_refunds_amount_positive"),
        Index("ix_refunds_order_issued", "order_id", "issued_at"),
    )

