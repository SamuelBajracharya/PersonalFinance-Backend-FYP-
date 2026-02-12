import random
import string
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from sqlalchemy import func
from app.models.voucher import UserVoucher, VoucherTemplate, VoucherStatus
from app.models.partner import Partner
from app.models.user_xp_milestone import UserXpMilestone
from app.models.user import User


def generate_unique_voucher_code():
    # Example: FIN-4F7K-92LA
    prefix = "FIN"
    part1 = "".join(random.choices(string.ascii_uppercase + string.digits, k=4))
    part2 = "".join(random.choices(string.ascii_uppercase + string.digits, k=4))
    return f"{prefix}-{part1}-{part2}"


def issue_voucher_to_user(
    db: Session,
    user_id: str,
    voucher_template: VoucherTemplate,
    source_type: str | None = None,
    source_id: str | None = None,
):
    code = generate_unique_voucher_code()
    issued_at = datetime.utcnow()
    expires_at = issued_at + timedelta(days=voucher_template.validity_days)
    user_voucher = UserVoucher(
        user_id=user_id,
        voucher_template_id=voucher_template.id,
        code=code,
        issued_at=issued_at,
        expires_at=expires_at,
        status=VoucherStatus.ACTIVE,
    )
    db.add(user_voucher)
    db.commit()
    db.refresh(user_voucher)
    # Log financial event if available
    try:
        from app.services.event_logger import log_event_async

        log_event_async(
            db,
            user_id,
            "voucher.issued",
            "voucher",
            str(user_voucher.id),
            {
                "voucher_template_id": str(voucher_template.id),
                "code": code,
                "expires_at": expires_at.isoformat(),
                "source_type": source_type,
                "source_id": source_id,
            },
        )
    except Exception:
        pass
    return user_voucher


def get_user_active_vouchers(db: Session, user_id: str):
    return (
        db.query(UserVoucher)
        .filter(
            UserVoucher.user_id == user_id,
            UserVoucher.status == VoucherStatus.ACTIVE,
            UserVoucher.expires_at > datetime.utcnow(),
        )
        .all()
    )


def _resolve_voucher_template_for_tier(
    db: Session, requested_tier: int | None
) -> VoucherTemplate | None:
    query = db.query(VoucherTemplate).filter(VoucherTemplate.is_active == True)

    if requested_tier is None:
        return query.order_by(VoucherTemplate.created_at.asc()).first()

    # Exact match first
    exact_match = (
        query.filter(VoucherTemplate.tier_required == requested_tier)
        .order_by(VoucherTemplate.created_at.asc())
        .first()
    )
    if exact_match:
        return exact_match

    # Fallback to closest lower tier
    lower_tier_match = (
        query.filter(
            VoucherTemplate.tier_required.isnot(None),
            VoucherTemplate.tier_required <= requested_tier,
        )
        .order_by(
            VoucherTemplate.tier_required.desc(), VoucherTemplate.created_at.asc()
        )
        .first()
    )
    if lower_tier_match:
        return lower_tier_match

    # Fallback to any active template
    return query.order_by(VoucherTemplate.created_at.asc()).first()


def issue_voucher_for_tier(
    db: Session,
    user_id: str,
    tier: int | None,
    source_type: str | None = None,
    source_id: str | None = None,
):
    template = _resolve_voucher_template_for_tier(db, tier)
    if not template:
        return None
    return issue_voucher_to_user(
        db,
        user_id,
        template,
        source_type=source_type,
        source_id=source_id,
    )


def derive_tier_from_xp(db: Session, total_xp: int) -> int | None:
    max_available_tier = (
        db.query(func.max(VoucherTemplate.tier_required))
        .filter(
            VoucherTemplate.is_active == True,
            VoucherTemplate.tier_required.isnot(None),
        )
        .scalar()
    )
    if not max_available_tier:
        return None

    # Tier progression by XP blocks of 2000, clamped to available tiers
    computed_tier = (total_xp // 2000) + 1
    return min(max(1, computed_tier), int(max_available_tier))
