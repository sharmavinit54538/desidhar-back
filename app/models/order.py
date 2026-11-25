import enum
import uuid
from datetime import date, datetime, timezone
from sqlalchemy import String, Integer, Text, DateTime, Enum, ForeignKey, CheckConstraint, Index, UniqueConstraint, Boolean, JSON, Date
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.core.db import Base


class OrderStatus(str, enum.Enum):
    payment_pending = "payment_pending"
    placed = "placed"
    confirmed = "confirmed"
    packed = "packed"
    shipped = "shipped"
    out_for_delivery = "out_for_delivery"
    delivered = "delivered"
    delivery_failed = "delivery_failed"
    cancelled = "cancelled"
    return_requested = "return_requested"
    return_approved = "return_approved"
    return_rejected = "return_rejected"
    return_in_transit = "return_in_transit"
    returned = "returned"


class PaymentMethod(str, enum.Enum):
    cod = "cod"
    online = "online"


class PaymentStatus(str, enum.Enum):
    pending = "pending"
    paid = "paid"
    failed = "failed"
    refunded = "refunded"
    partially_refunded = "partially_refunded"
    partially_paid = "partially_paid"
    refund_pending = "refund_pending"


class Order(Base):
    __tablename__ = "orders"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    order_number: Mapped[str] = mapped_column(String(30), unique=True, nullable=False, index=True)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    status: Mapped[OrderStatus] = mapped_column(Enum(OrderStatus, native_enum=False, length=30), default=OrderStatus.placed, nullable=False)
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
    version: Mapped[int] = mapped_column(Integer, default=1, server_default="1", nullable=False)
    stock_reserved: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true", nullable=False)
    stock_released: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false", nullable=False)
    return_restocked: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false", nullable=False)
    billing_address: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    placed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    packed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    shipped_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    out_for_delivery_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    estimated_delivery_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    estimated_delivery_end_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    revised_delivery_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    delay_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
    delivery_speed: Mapped[str] = mapped_column(String(20), default="standard", server_default="standard", nullable=False)
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cancel_reason: Mapped[str | None] = mapped_column(String(255), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)

    items = relationship("OrderItem", lazy="selectin", cascade="all, delete-orphan")
    history = relationship("OrderStatusHistory", lazy="selectin", order_by="OrderStatusHistory.created_at", cascade="all, delete-orphan")
    payments = relationship("Payment", lazy="selectin", cascade="all, delete-orphan")
    refunds = relationship("Refund", lazy="selectin", cascade="all, delete-orphan")
    customer = relationship("User", lazy="selectin")
    shipment = relationship("Shipment", lazy="selectin", uselist=False)
    invoice = relationship("Invoice", lazy="selectin", uselist=False)

    @property
    def amount_paid_paise(self) -> int:
        return sum(payment.amount_paise for payment in self.payments if payment.paid_at is not None)

    @property
    def outstanding_paise(self) -> int:
        return max(0, self.total_paise - self.amount_paid_paise)

    @property
    def outstanding_amount_paise(self) -> int:
        return self.outstanding_paise

    @property
    def refunded_amount_paise(self) -> int:
        return sum(refund.amount_paise for refund in self.refunds if refund.status == "completed")

    @property
    def customer_email(self) -> str | None:
        return self.customer.email if self.customer else None

    @property
    def invoice_available(self) -> bool:
        return self.invoice is not None

    @property
    def delivery_status(self) -> str:
        return self.shipment.shipment_status if self.shipment else self.status.value

    @property
    def actual_delivery_date(self) -> datetime | None:
        return self.delivered_at

    @property
    def allowed_next_statuses(self) -> list[str]:
        from app.services.order_transition import ALLOWED_TRANSITIONS
        curr = self.status.value if hasattr(self.status, "value") else str(self.status)
        return sorted(list(ALLOWED_TRANSITIONS.get(curr, set())))

    @property
    def allowed_actions(self) -> list[str]:
        return self.allowed_next_statuses

    __table_args__ = (
        CheckConstraint("total_paise = subtotal_paise - discount_paise + delivery_fee_paise", name="ck_orders_total_consistency"),
        UniqueConstraint("user_id", "idempotency_key", name="uq_orders_user_idempotency"),
        Index("ix_orders_user_placed", "user_id", "placed_at"),
        Index("ix_orders_status_placed", "status", "placed_at"),
    )

