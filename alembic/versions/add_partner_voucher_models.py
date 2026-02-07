"""
Add Partner, VoucherTemplate, UserVoucher, UserXpMilestone models
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
import uuid


def upgrade():
    op.create_table(
        "partners",
        sa.Column(
            "id", postgresql.UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
        ),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("logo_url", sa.String(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")
        ),
    )
    op.create_table(
        "voucher_templates",
        sa.Column(
            "id", postgresql.UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
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
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")
        ),
    )
    op.create_table(
        "user_vouchers",
        sa.Column(
            "id", postgresql.UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
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
            "issued_at", sa.DateTime(timezone=True), server_default=sa.text("now()")
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "status",
            sa.Enum("ACTIVE", "REDEEMED", "EXPIRED", name="voucherstatus"),
            nullable=False,
            server_default="ACTIVE",
        ),
    )
    op.create_table(
        "user_xp_milestones",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("user_id", sa.String(), nullable=False, index=True),
        sa.Column("milestone", sa.Integer(), nullable=False),
        sa.Column(
            "achieved_at", sa.DateTime(timezone=True), server_default=sa.text("now()")
        ),
    )


def downgrade():
    op.drop_table("user_xp_milestones")
    op.drop_table("user_vouchers")
    op.drop_table("voucher_templates")
    op.drop_table("partners")
    op.execute("DROP TYPE IF EXISTS discounttype")
    op.execute("DROP TYPE IF EXISTS voucherstatus")
