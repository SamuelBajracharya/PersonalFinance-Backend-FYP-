"""
Add Partner, VoucherTemplate, UserVoucher, UserXpMilestone models
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
import uuid


# revision identifiers, used by Alembic.
revision: str = "a7f9c91d2b31"
down_revision: Union[str, Sequence[str], None] = "d4f19f2d7a21"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_tables = set(inspector.get_table_names())

    if "partners" not in existing_tables:
        op.create_table(
            "partners",
            sa.Column(
                "id",
                postgresql.UUID(as_uuid=True),
                primary_key=True,
                default=uuid.uuid4,
            ),
            sa.Column("name", sa.String(), nullable=False),
            sa.Column("description", sa.Text(), nullable=False),
            sa.Column("logo_url", sa.String(), nullable=True),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.text("now()"),
            ),
        )

    if "voucher_templates" not in existing_tables:
        op.create_table(
            "voucher_templates",
            sa.Column(
                "id",
                postgresql.UUID(as_uuid=True),
                primary_key=True,
                default=uuid.uuid4,
            ),
            sa.Column(
                "partner_id",
                postgresql.UUID(as_uuid=True),
                sa.ForeignKey("partners.id"),
                nullable=False,
            ),
            sa.Column("title", sa.String(), nullable=False),
            sa.Column("description", sa.String(), nullable=False),
            sa.Column(
                "discount_type",
                sa.Enum("PERCENTAGE", "FIXED_AMOUNT", name="discounttype"),
                nullable=False,
            ),
            sa.Column("discount_value", sa.Float(), nullable=False),
            sa.Column("minimum_spend", sa.Float(), nullable=True),
            sa.Column("tier_required", sa.Integer(), nullable=True),
            sa.Column("xp_required", sa.Integer(), nullable=True),
            sa.Column("validity_days", sa.Integer(), nullable=False),
            sa.Column("is_active", sa.Boolean(), nullable=False, default=True),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.text("now()"),
            ),
        )

    if "user_vouchers" not in existing_tables:
        op.create_table(
            "user_vouchers",
            sa.Column(
                "id",
                postgresql.UUID(as_uuid=True),
                primary_key=True,
                default=uuid.uuid4,
            ),
            sa.Column(
                "user_id", sa.String(), sa.ForeignKey("users.user_id"), nullable=False
            ),
            sa.Column(
                "voucher_template_id",
                postgresql.UUID(as_uuid=True),
                sa.ForeignKey("voucher_templates.id"),
                nullable=False,
            ),
            sa.Column("code", sa.String(), unique=True, nullable=False),
            sa.Column(
                "issued_at",
                sa.DateTime(timezone=True),
                server_default=sa.text("now()"),
            ),
            sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column(
                "status",
                sa.Enum("ACTIVE", "REDEEMED", "EXPIRED", name="voucherstatus"),
                nullable=False,
                server_default="ACTIVE",
            ),
        )

    if "user_xp_milestones" not in existing_tables:
        op.create_table(
            "user_xp_milestones",
            sa.Column("id", sa.String(), primary_key=True),
            sa.Column("user_id", sa.String(), nullable=False, index=True),
            sa.Column("milestone", sa.Integer(), nullable=False),
            sa.Column(
                "achieved_at",
                sa.DateTime(timezone=True),
                server_default=sa.text("now()"),
            ),
        )


def downgrade():
    op.execute("DROP TABLE IF EXISTS user_xp_milestones")
    op.execute("DROP TABLE IF EXISTS user_vouchers")
    op.execute("DROP TABLE IF EXISTS voucher_templates")
    op.execute("DROP TABLE IF EXISTS partners")
    op.execute("DROP TYPE IF EXISTS discounttype")
    op.execute("DROP TYPE IF EXISTS voucherstatus")
