import enum
import uuid
from datetime import datetime
from typing import ClassVar

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    # Every Mapped[datetime] column is `timestamptz`; naive datetimes are a recurring source
    # of "which timezone is this" bugs, so the app only ever writes timezone-aware UTC values.
    type_annotation_map: ClassVar[dict[type, object]] = {datetime: DateTime(timezone=True)}


def _enum_values(enum_cls: type[enum.StrEnum]) -> list[str]:
    # Without this, SQLAlchemy stores the Python member NAME ("REFUND_REQUEST") in the Postgres
    # enum type, not member.value ("refund_request"); raw SQL elsewhere (the partial index
    # below, hand-written queries) expects the lowercase value.
    return [member.value for member in enum_cls]


class ListingStatus(enum.StrEnum):
    ACTIVE = "active"
    INACTIVE = "inactive"
    SUPPRESSED = "suppressed"


class OrderStatus(enum.StrEnum):
    PENDING = "pending"
    SHIPPED = "shipped"
    DELIVERED = "delivered"
    CANCELLED = "cancelled"
    REFUND_REQUESTED = "refund_requested"
    REFUNDED = "refunded"


class CaseType(enum.StrEnum):
    REFUND_REQUEST = "refund_request"
    ESCALATION = "escalation"
    OTHER = "other"


class CaseStatus(enum.StrEnum):
    OPEN = "open"
    IN_PROGRESS = "in_progress"
    RESOLVED = "resolved"


class Seller(Base):
    __tablename__ = "sellers"

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    email: Mapped[str] = mapped_column(unique=True)
    display_name: Mapped[str]
    cognito_sub: Mapped[str | None] = mapped_column(unique=True)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    listings: Mapped[list["Listing"]] = relationship(back_populates="seller")
    orders: Mapped[list["Order"]] = relationship(back_populates="seller")
    support_cases: Mapped[list["SupportCase"]] = relationship(back_populates="seller")


class Listing(Base):
    __tablename__ = "listings"
    __table_args__ = (
        UniqueConstraint("seller_id", "sku", name="uq_listings_seller_sku"),
        CheckConstraint("price_cents >= 0", name="ck_listings_price_cents_nonneg"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    seller_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("sellers.id", ondelete="RESTRICT")
    )
    sku: Mapped[str]
    title: Mapped[str]
    price_cents: Mapped[int]
    status: Mapped[ListingStatus] = mapped_column(
        Enum(ListingStatus, name="listing_status", native_enum=True, values_callable=_enum_values)
    )
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    seller: Mapped["Seller"] = relationship(back_populates="listings")


class Order(Base):
    __tablename__ = "orders"
    __table_args__ = (
        CheckConstraint("total_cents >= 0", name="ck_orders_total_cents_nonneg"),
        CheckConstraint(
            "delivered_at IS NULL OR delivered_at >= placed_at",
            name="ck_orders_delivered_at_after_placed_at",
        ),
        Index("ix_orders_seller_id_placed_at", "seller_id", text("placed_at DESC")),
        Index("ix_orders_seller_id_status", "seller_id", "status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    seller_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("sellers.id", ondelete="RESTRICT")
    )
    buyer_ref: Mapped[str]
    status: Mapped[OrderStatus] = mapped_column(
        Enum(OrderStatus, name="order_status", native_enum=True, values_callable=_enum_values)
    )
    total_cents: Mapped[int]
    currency: Mapped[str]
    placed_at: Mapped[datetime]
    delivered_at: Mapped[datetime | None]
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())

    seller: Mapped["Seller"] = relationship(back_populates="orders")
    items: Mapped[list["OrderItem"]] = relationship(back_populates="order")
    support_cases: Mapped[list["SupportCase"]] = relationship(back_populates="order")


class OrderItem(Base):
    __tablename__ = "order_items"
    __table_args__ = (
        CheckConstraint("quantity > 0", name="ck_order_items_quantity_pos"),
        CheckConstraint("unit_price_cents >= 0", name="ck_order_items_unit_price_cents_nonneg"),
    )

    order_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("orders.id", ondelete="RESTRICT"), primary_key=True
    )
    listing_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("listings.id", ondelete="RESTRICT"), primary_key=True
    )
    quantity: Mapped[int]
    unit_price_cents: Mapped[int]

    order: Mapped["Order"] = relationship(back_populates="items")
    listing: Mapped["Listing"] = relationship()


class SupportCase(Base):
    __tablename__ = "support_cases"
    __table_args__ = (
        # One non-resolved refund_request case per order; resolved cases don't block a new one.
        Index(
            "uq_support_cases_one_open_refund_per_order",
            "order_id",
            unique=True,
            postgresql_where=text("type = 'refund_request' AND status != 'resolved'"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    seller_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("sellers.id", ondelete="RESTRICT")
    )
    order_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("orders.id", ondelete="RESTRICT")
    )
    type: Mapped[CaseType] = mapped_column(
        Enum(CaseType, name="case_type", native_enum=True, values_callable=_enum_values)
    )
    status: Mapped[CaseStatus] = mapped_column(
        Enum(CaseStatus, name="case_status", native_enum=True, values_callable=_enum_values),
        default=CaseStatus.OPEN,
    )
    description: Mapped[str]
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    seller: Mapped["Seller"] = relationship(back_populates="support_cases")
    order: Mapped["Order | None"] = relationship(back_populates="support_cases")
