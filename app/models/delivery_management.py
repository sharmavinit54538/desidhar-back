"""Delivery partner operations and immutable assignment history."""
import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, String, Integer, DateTime, ForeignKey, JSON, Index, CheckConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship, foreign

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
    is_suspended: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false", nullable=False)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)

    user = relationship("User", lazy="selectin")

    __table_args__ = (
        CheckConstraint("max_active_deliveries > 0", name="ck_delivery_partner_capacity_positive"),
        CheckConstraint("availability IN ('available', 'offline')", name="ck_delivery_partner_availability"),
    )


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

    partner = relationship("User", foreign_keys=[partner_id], lazy="selectin")
    partner_profile = relationship(
        "DeliveryPartnerProfile",
        primaryjoin="foreign(DeliveryAssignment.partner_id) == DeliveryPartnerProfile.user_id",
        lazy="selectin",
        viewonly=True,
        uselist=False,
    )
    assigned_by_user = relationship("User", foreign_keys=[assigned_by], lazy="selectin")
    history = relationship(
        "DeliveryAssignmentHistory",
        lazy="selectin",
        order_by="DeliveryAssignmentHistory.created_at",
    )

    @property
    def partner_name(self) -> str | None:
        return self.partner.full_name if self.partner else None

    @property
    def partner_phone(self) -> str | None:
        return self.partner.phone if self.partner else None

    @property
    def partner_employee_id(self) -> str | None:
        return self.partner_profile.employee_id if self.partner_profile else None

    @property
    def partner_service_area(self) -> str | None:
        return self.partner_profile.service_area if self.partner_profile else None

    @property
    def partner_availability(self) -> str | None:
        return self.partner_profile.availability if self.partner_profile else None

    @property
    def assigned_by_name(self) -> str | None:
        if not self.assigned_by_user:
            return None
        return self.assigned_by_user.full_name or self.assigned_by_user.username

    __table_args__ = (
        Index("ix_delivery_assignments_partner_status", "partner_id", "status"),
        Index("ix_delivery_assignments_order", "order_id", "assigned_at"),
        Index("uq_delivery_active_assignment_order", "order_id", unique=True,
              postgresql_where=(status.in_(["assigned", "accepted", "picked_up", "in_progress"]))),
        CheckConstraint("version > 0", name="ck_delivery_assignment_version_positive"),
        CheckConstraint(
            "status IN ('assigned', 'accepted', 'picked_up', 'in_progress', 'completed', 'failed', 'rejected', 'cancelled')",
            name="ck_delivery_assignment_status",
        ),
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

    actor = relationship("User", foreign_keys=[actor_id], lazy="selectin")

    @property
    def actor_name(self) -> str | None:
        if not self.actor:
            return None
        return self.actor.full_name or self.actor.username

    __table_args__ = (Index("ix_delivery_assignment_history_order", "order_id", "created_at"),)
