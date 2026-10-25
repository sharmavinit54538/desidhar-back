import uuid
from sqlalchemy import ForeignKey, Index
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from app.core.db import Base


class ProductPincode(Base):
    __tablename__ = "product_pincodes"

    product_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("products.id", ondelete="CASCADE"), primary_key=True)
    pincode_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("pincodes.id", ondelete="CASCADE"), primary_key=True)

    __table_args__ = (
        Index("ix_product_pincodes_pincode_id", "pincode_id"),
    )
