"""add profile_image_url to users

Revision ID: b6c3f9b2e4d1
Revises: a7f9c91d2b31, 3add_time_horizon
Create Date: 2026-04-04 00:00:00.000000

"""

from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "b6c3f9b2e4d1"
down_revision: Union[str, Sequence[str], None] = ("a7f9c91d2b31", "3add_time_horizon")
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS profile_image_url VARCHAR")


def downgrade() -> None:
    op.execute("ALTER TABLE users DROP COLUMN IF EXISTS profile_image_url")
