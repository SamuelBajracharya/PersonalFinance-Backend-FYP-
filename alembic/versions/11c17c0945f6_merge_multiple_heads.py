"""Merge multiple heads

Revision ID: 11c17c0945f6
Revises: 368f34f5aa21, e8b6b4b6b1b1
Create Date: 2026-02-01 00:16:53.143757

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '11c17c0945f6'
down_revision: Union[str, Sequence[str], None] = ('368f34f5aa21', 'e8b6b4b6b1b1')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
