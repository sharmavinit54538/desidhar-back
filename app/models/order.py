import enum
import uuid
from datetime import datetime, timezone
from sqlalchemy import String, Integer, Text, DateTime, Enum, ForeignKey, CheckConstraint, Index, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.core.db import Base


class OrderStatus(str, enum.Enum):
    payment_pending = "payment_pending"
    placed = "placed"
    confirmed = "confirmed"
    packed = "packed"
    out_for_delivery = "out_for_delivery"
    delivered = "delivered"
    delivery_failed = "delivery_failed"
    cancelled = "cancelled"


class PaymentMethod(str, enum.Enum):
    cod = "cod"
    online = "online"


class PaymentStatus(str, enum.Enum):
    pending = "pending"
    paid = "paid"
    failed = "failed"
    refunded = "refunded"
    partially_refunded = "partially_refunded"


class Order(Base):
    __tablename__ = "orders"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    order_number: Mapped[str] = mapped_column(String(30), unique=True, nullable=False, index=True)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    status: Mapped[OrderStatus] = mapped_column(Enum(OrderStatus, native_enum=False), default=OrderStatus.placed, nullable=False)
    payment_method: Mapped[PaymentMethod] = mapped_column(Enum(PaymentMethod, native_enum=False), nullable=False)
    payment_status: Mapped[PaymentStatus] = mapped_column(Enum(PaymentStatus, native_enum=False), default=PaymentStatus.pending, nullable=False)

    shipping_name: Mapped[str] = mapped_column(String(100), nullable=False)
    shipping_phone: Mapped[str] = mapped_column(String(15), nullable=False)
    shipping_line1: Mapped[str] = mapped_column(String(255), nullable=False)
    shipping_line2: Mapped[str | None] = mapped_column(String(255), nullable=True)
    shipping_landmark: Mapped[str | None] = mapped_column(String(255), nullable=True)
    shipping_city: Mapped[str] = mapped_column(String(100), nullable=False)
    shipping_state: Mapped[str] = mapped_column(String(100), nullable=False)
    shipping_pincode: Mapped[str] = mapped_column(String(6), nullable=False, index=True)

    subtotal_paise: Mapped[int] = mapped_column(Integer, nullable=False)
    discount_paise: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    coupon_code: Mapped[str | None] = mapped_column(String(50), nullable=True)
    delivery_fee_paise: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_paise: Mapped[int] = mapped_column(Integer, nullable=False)
    tax_paise: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    idempotency_key: Mapped[str | None] = mapped_column(String(100), nullable=True)

    placed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cancel_reason: Mapped[str | None] = mapped_column(String(255), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)

    items = relationship("OrderItem", lazy="selectin", cascade="all, delete-orphan")
    history = relationship("OrderStatusHistory", lazy="selectin", order_by="OrderStatusHistory.created_at", cascade="all, delete-orphan")
    payments = relationship("Payment", lazy="selectin", cascade="all, delete-orphan")
    refunds = relationship("Refund", lazy="selectin", cascade="all, delete-orphan")

    __table_args__ = (
        CheckConstraint("total_paise = subtotal_paise - discount_paise + delivery_fee_paise", name="ck_orders_total_consistency"),
        UniqueConstraint("user_id", "idempotency_key", name="uq_orders_user_idempotency"),
        Index("ix_orders_user_placed", "user_id", "placed_at"),
        Index("ix_orders_status_placed", "status", "placed_at"),
    )
