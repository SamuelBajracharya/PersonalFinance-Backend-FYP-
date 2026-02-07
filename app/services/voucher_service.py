import random
import string
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
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


def issue_voucher_to_user(db: Session, user_id: str, voucher_template: VoucherTemplate):
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
