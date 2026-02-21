"""add bank_token to bank_accounts

Revision ID: d4f19f2d7a21
Revises: c2a7b6b8b8b1
Create Date: 2026-02-21 00:10:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "d4f19f2d7a21"
down_revision: Union[str, Sequence[str], None] = "c2a7b6b8b8b1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TABLE bank_accounts ADD COLUMN IF NOT EXISTS bank_token VARCHAR")


def downgrade() -> None:
    op.execute("ALTER TABLE bank_accounts DROP COLUMN IF EXISTS bank_token")
