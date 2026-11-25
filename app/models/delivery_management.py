"""Delivery partner operations and immutable assignment history."""
import uuid
from datetime import datetime, timezone

from sqlalchemy import String, Integer, DateTime, ForeignKey, JSON, Index, CheckConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class DeliveryPartnerProfile(Base):
    __tablename__ = "delivery_partner_profiles"

    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), primary_key=True)
    employee_id: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    service_area: Mapped[str | None] = mapped_column(String(150), nullable=True)
    service_pincodes: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    vehicle_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    vehicle_registration: Mapped[str | None] = mapped_column(String(30), nullable=True)
    max_active_deliveries: Mapped[int] = mapped_column(Integer, default=10, server_default="10", nullable=False)
    availability: Mapped[str] = mapped_column(String(20), default="offline", server_default="offline", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)

    __table_args__ = (CheckConstraint("max_active_deliveries > 0", name="ck_delivery_partner_capacity_positive"),)


class DeliveryAssignment(Base):
    __tablename__ = "delivery_assignments"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    order_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("orders.id", ondelete="RESTRICT"), nullable=False)
    partner_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    assigned_by: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="assigned", server_default="assigned", nullable=False)
    version: Mapped[int] = mapped_column(Integer, default=1, server_default="1", nullable=False)
    assigned_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    picked_up_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    failure_reason: Mapped[str | None] = mapped_column(String(255), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)

    __table_args__ = (
        Index("ix_delivery_assignments_partner_status", "partner_id", "status"),
        Index("ix_delivery_assignments_order", "order_id", "assigned_at"),
        Index("uq_delivery_active_assignment_order", "order_id", unique=True,
              postgresql_where=(status.in_(["assigned", "accepted", "picked_up", "in_progress"]))),
        CheckConstraint("version > 0", name="ck_delivery_assignment_version_positive"),
    )


class DeliveryAssignmentHistory(Base):
    __tablename__ = "delivery_assignment_history"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    assignment_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("delivery_assignments.id", ondelete="RESTRICT"), nullable=False)
    order_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("orders.id", ondelete="RESTRICT"), nullable=False)
    actor_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    from_status: Mapped[str | None] = mapped_column(String(20), nullable=True)
    to_status: Mapped[str] = mapped_column(String(20), nullable=False)
    note: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    __table_args__ = (Index("ix_delivery_assignment_history_order", "order_id", "created_at"),)
