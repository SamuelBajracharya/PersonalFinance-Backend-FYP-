"""add_is_completed_to_budgets

Revision ID: 368f34f5aa21
Revises: 9eeafb443542
Create Date: 2026-01-08 14:36:14.260995

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '368f34f5aa21'
down_revision: Union[str, Sequence[str], None] = '9eeafb443542'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('budgets', sa.Column('is_completed', sa.Boolean(), nullable=False, server_default=sa.false()))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('budgets', 'is_completed')
