"""add_goals_completed_to_users

Revision ID: 9eeafb443542
Revises: 6ae1b28d45ae
Create Date: 2026-01-08 14:34:20.128312

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '9eeafb443542'
down_revision: Union[str, Sequence[str], None] = '6ae1b28d45ae'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('users', sa.Column('goals_completed', sa.Integer(), nullable=False, server_default='0'))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('users', 'goals_completed')
