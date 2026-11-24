import uuid
from datetime import datetime, timezone
from sqlalchemy import String, DateTime, ForeignKey, Index, UniqueConstraint, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from app.core.db import Base


class OrderStatusHistory(Base):
    __tablename__ = "order_status_history"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    order_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("orders.id", ondelete="CASCADE"), nullable=False)
    from_status: Mapped[str | None] = mapped_column(String(30), nullable=True)
    to_status: Mapped[str] = mapped_column(String(30), nullable=False)
    changed_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    note: Mapped[str | None] = mapped_column(String(255), nullable=True)
    actor_type: Mapped[str] = mapped_column(String(20), default="system", server_default="system", nullable=False)
    reason: Mapped[str | None] = mapped_column(String(255), nullable=True)
    customer_visible_message: Mapped[str | None] = mapped_column(String(500), nullable=True)
    internal_admin_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    event_source: Mapped[str] = mapped_column(String(30), default="legacy", server_default="legacy", nullable=False)
    idempotency_key: Mapped[str | None] = mapped_column(String(100), nullable=True)
    request_fingerprint: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)

    __table_args__ = (
        Index("ix_order_status_history_order_id", "order_id"),
        UniqueConstraint("order_id", "idempotency_key", name="uq_order_history_idempotency"),
    )

