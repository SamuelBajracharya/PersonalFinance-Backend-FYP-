"""add time_horizon to daily_predictions

Revision ID: 3add_time_horizon
Revises: 2f4d2f9fb9a1
Create Date: 2026-02-07 23:00:00.000000

"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "3add_time_horizon"
down_revision = "2f4d2f9fb9a1"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "daily_predictions",
        sa.Column(
            "time_horizon", sa.String(length=32), nullable=False, server_default="30d"
        ),
    )


def downgrade():
    op.drop_column("daily_predictions", "time_horizon")
