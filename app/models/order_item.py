import uuid
from decimal import Decimal
from sqlalchemy import String, Integer, Numeric, ForeignKey, Index, CheckConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.core.db import Base


class OrderItem(Base):
    __tablename__ = "order_items"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    order_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("orders.id", ondelete="CASCADE"), nullable=False)
    product_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("products.id", ondelete="RESTRICT"), nullable=False)

    name_snapshot: Mapped[str] = mapped_column(String(200), nullable=False)
    pack_size_snapshot: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    unit_snapshot: Mapped[str] = mapped_column(String(20), nullable=False)
    sku_snapshot: Mapped[str | None] = mapped_column(String(220), nullable=True)
    image_url_snapshot: Mapped[str | None] = mapped_column(String(2048), nullable=True)

    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    unit_price_paise: Mapped[int] = mapped_column(Integer, nullable=False)
    unit_mrp_paise: Mapped[int] = mapped_column(Integer, nullable=False)
    unit_cost_paise: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    gst_rate_percent: Mapped[Decimal] = mapped_column(Numeric(5, 2), default=Decimal("0.00"), nullable=False)

    discount_paise: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    tax_paise: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    line_total_paise: Mapped[int] = mapped_column(Integer, nullable=False)

    product = relationship("Product", lazy="selectin")

    @property
    def image_url(self) -> str | None:
        if self.image_url_snapshot:
            return self.image_url_snapshot
        if self.product and self.product.images:
            return self.product.images[0].url
        return None

    @property
    def sku(self) -> str | None:
        return self.sku_snapshot

    @property
    def product_slug(self) -> str | None:
        if self.product:
            return self.product.slug
        return None

    __table_args__ = (
        CheckConstraint("quantity > 0", name="ck_order_items_qty_positive"),
        Index("ix_order_items_order_id", "order_id"),
        Index("ix_order_items_product_id", "product_id"),
    )

