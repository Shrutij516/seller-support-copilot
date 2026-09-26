"""initial schema

Revision ID: 95d6744ed870
Revises:
Create Date: 2026-09-26 16:02:33.060320

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "95d6744ed870"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "sellers",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("email", sa.String(), nullable=False),
        sa.Column("display_name", sa.String(), nullable=False),
        sa.Column("cognito_sub", sa.String(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("cognito_sub"),
        sa.UniqueConstraint("email"),
    )
    op.create_table(
        "listings",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("seller_id", sa.UUID(), nullable=False),
        sa.Column("sku", sa.String(), nullable=False),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("price_cents", sa.Integer(), nullable=False),
        sa.Column(
            "status",
            sa.Enum("active", "inactive", "suppressed", name="listing_status"),
            nullable=False,
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.CheckConstraint("price_cents >= 0", name="ck_listings_price_cents_nonneg"),
        sa.ForeignKeyConstraint(["seller_id"], ["sellers.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("seller_id", "sku", name="uq_listings_seller_sku"),
    )
    op.create_table(
        "orders",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("seller_id", sa.UUID(), nullable=False),
        sa.Column("buyer_ref", sa.String(), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "pending",
                "shipped",
                "delivered",
                "cancelled",
                "refund_requested",
                "refunded",
                name="order_status",
            ),
            nullable=False,
        ),
        sa.Column("total_cents", sa.Integer(), nullable=False),
        sa.Column("currency", sa.String(), nullable=False),
        sa.Column("placed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            onupdate=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("total_cents >= 0", name="ck_orders_total_cents_nonneg"),
        sa.ForeignKeyConstraint(["seller_id"], ["sellers.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_orders_seller_id_placed_at",
        "orders",
        ["seller_id", sa.literal_column("placed_at DESC")],
        unique=False,
    )
    op.create_index("ix_orders_seller_id_status", "orders", ["seller_id", "status"], unique=False)
    op.create_table(
        "order_items",
        sa.Column("order_id", sa.UUID(), nullable=False),
        sa.Column("listing_id", sa.UUID(), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("unit_price_cents", sa.Integer(), nullable=False),
        sa.CheckConstraint("quantity > 0", name="ck_order_items_quantity_pos"),
        sa.CheckConstraint("unit_price_cents >= 0", name="ck_order_items_unit_price_cents_nonneg"),
        sa.ForeignKeyConstraint(["listing_id"], ["listings.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["order_id"], ["orders.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("order_id", "listing_id"),
    )
    op.create_table(
        "support_cases",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("seller_id", sa.UUID(), nullable=False),
        sa.Column("order_id", sa.UUID(), nullable=True),
        sa.Column(
            "type",
            sa.Enum("refund_request", "escalation", "other", name="case_type"),
            nullable=False,
        ),
        sa.Column(
            "status",
            sa.Enum("open", "in_progress", "resolved", name="case_status"),
            nullable=False,
        ),
        sa.Column("description", sa.String(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.ForeignKeyConstraint(["order_id"], ["orders.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["seller_id"], ["sellers.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "uq_support_cases_one_open_refund_per_order",
        "support_cases",
        ["order_id"],
        unique=True,
        postgresql_where=sa.text("type = 'refund_request' AND status != 'resolved'"),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(
        "uq_support_cases_one_open_refund_per_order",
        table_name="support_cases",
        postgresql_where=sa.text("type = 'refund_request' AND status != 'resolved'"),
    )
    op.drop_table("support_cases")
    op.drop_table("order_items")
    op.drop_index("ix_orders_seller_id_status", table_name="orders")
    op.drop_index("ix_orders_seller_id_placed_at", table_name="orders")
    op.drop_table("orders")
    op.drop_table("listings")
    op.drop_table("sellers")
    # Native Postgres enum types outlive drop_table and must be dropped explicitly.
    bind = op.get_bind()
    sa.Enum(name="case_status").drop(bind)
    sa.Enum(name="case_type").drop(bind)
    sa.Enum(name="order_status").drop(bind)
    sa.Enum(name="listing_status").drop(bind)
