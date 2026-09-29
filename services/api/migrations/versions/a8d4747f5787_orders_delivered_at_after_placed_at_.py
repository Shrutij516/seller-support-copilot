"""orders delivered_at after placed_at check

Revision ID: a8d4747f5787
Revises: 95d6744ed870
Create Date: 2026-09-29 18:10:38.385402

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a8d4747f5787"
down_revision: str | Sequence[str] | None = "95d6744ed870"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_check_constraint(
        "ck_orders_delivered_at_after_placed_at",
        "orders",
        "delivered_at IS NULL OR delivered_at >= placed_at",
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint("ck_orders_delivered_at_after_placed_at", "orders", type_="check")
