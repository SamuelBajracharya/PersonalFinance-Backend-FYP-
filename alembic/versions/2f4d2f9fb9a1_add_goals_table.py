"""Add goals table

Revision ID: 2f4d2f9fb9a1
Revises: 5fe5af8b26e2
Create Date: 2026-02-07 00:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "2f4d2f9fb9a1"
down_revision: Union[str, Sequence[str], None] = "5fe5af8b26e2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    goal_type_enum = postgresql.ENUM(
        "SAVINGS",
        "EMERGENCY",
        "TRAVEL",
        "DEBT",
        name="goaltype",
        create_type=False,
    )
    goal_status_enum = postgresql.ENUM(
        "ACTIVE",
        "AT_RISK",
        "ACHIEVED",
        "EXPIRED",
        name="goalstatus",
        create_type=False,
    )
    goal_type_enum.create(op.get_bind(), checkfirst=True)
    goal_status_enum.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "goals",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("goal_type", goal_type_enum, nullable=False),
        sa.Column("target_amount", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column("current_amount", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column("deadline", sa.Date(), nullable=False),
        sa.Column("status", goal_status_enum, nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=True,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=True,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.user_id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_goals_user_id"), "goals", ["user_id"], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f("ix_goals_user_id"), table_name="goals")
    op.drop_table("goals")
    goal_status_enum = postgresql.ENUM(
        "ACTIVE",
        "AT_RISK",
        "ACHIEVED",
        "EXPIRED",
        name="goalstatus",
        create_type=False,
    )
    goal_type_enum = postgresql.ENUM(
        "SAVINGS",
        "EMERGENCY",
        "TRAVEL",
        "DEBT",
        name="goaltype",
        create_type=False,
    )
    goal_status_enum.drop(op.get_bind(), checkfirst=True)
    goal_type_enum.drop(op.get_bind(), checkfirst=True)
