"""add stock instruments table

Revision ID: c2a7b6b8b8b1
Revises: 11c17c0945f6
Create Date: 2026-02-21 00:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "c2a7b6b8b8b1"
down_revision: Union[str, Sequence[str], None] = "11c17c0945f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_tables = set(inspector.get_table_names())

    if "stock_instruments" not in existing_tables:
        op.create_table(
            "stock_instruments",
            sa.Column(
                "id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False
            ),
            sa.Column(
                "user_id", sa.String(), sa.ForeignKey("users.user_id"), nullable=False
            ),
            sa.Column("symbol", sa.String(length=20), nullable=False),
            sa.Column("name", sa.String(), nullable=True),
            sa.Column("quantity", sa.Numeric(precision=18, scale=6), nullable=False),
            sa.Column(
                "average_buy_price", sa.Numeric(precision=18, scale=6), nullable=True
            ),
            sa.Column(
                "current_price", sa.Numeric(precision=18, scale=6), nullable=True
            ),
            sa.Column("currency", sa.String(length=10), nullable=True),
            sa.Column("external_instrument_id", sa.String(), nullable=True),
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                server_default=sa.text("now()"),
                nullable=True,
            ),
            sa.UniqueConstraint("user_id", "symbol", name="uq_user_symbol"),
        )

    existing_indexes = (
        {index["name"] for index in inspector.get_indexes("stock_instruments")}
        if "stock_instruments" in set(inspector.get_table_names())
        else set()
    )
    if "ix_stock_instruments_user_id" not in existing_indexes:
        op.create_index(
            "ix_stock_instruments_user_id",
            "stock_instruments",
            ["user_id"],
            unique=False,
        )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_stock_instruments_user_id")
    op.execute("DROP TABLE IF EXISTS stock_instruments")
