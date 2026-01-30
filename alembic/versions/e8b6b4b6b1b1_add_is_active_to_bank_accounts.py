"""add is_active to bank accounts

Revision ID: e8b6b4b6b1b1
Revises: 9eeafb443542
Create Date: 2026-01-30 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'e8b6b4b6b1b1'
down_revision = '9eeafb443542'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('bank_accounts', sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'))
    op.alter_column('bank_accounts', 'is_active', server_default=None)


def downgrade() -> None:
    op.drop_column('bank_accounts', 'is_active')
