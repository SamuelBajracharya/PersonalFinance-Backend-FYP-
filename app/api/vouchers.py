from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.utils.deps import get_db, get_current_user
from app.services.voucher_service import (
    get_user_active_vouchers,
    issue_voucher_to_user,
    generate_unique_voucher_code,
)
from app.models.voucher import UserVoucher, VoucherStatus, VoucherTemplate
from app.models.partner import Partner
from app.models.user import User
from datetime import datetime

router = APIRouter()


@router.get("/available")
def get_available_voucher_templates(db: Session = Depends(get_db)):
    return db.query(VoucherTemplate).filter(VoucherTemplate.is_active == True).all()


@router.get("/me")
def get_my_vouchers(
    db: Session = Depends(get_db), current_user: User = Depends(get_current_user)
):
    vouchers = get_user_active_vouchers(db, current_user.user_id)
    result = []
    for v in vouchers:
        template = (
            db.query(VoucherTemplate)
            .filter(VoucherTemplate.id == v.voucher_template_id)
            .first()
        )
        result.append(
            {
                "id": str(v.id),
                "code": v.code,
                "issued_at": v.issued_at,
                "expires_at": v.expires_at,
                "status": v.status,
                "title": template.title if template else None,
                "description": template.description if template else None,
                "discount_type": template.discount_type if template else None,
                "discount_value": template.discount_value if template else None,
                "partner_id": str(template.partner_id) if template else None,
            }
        )
    return result


@router.get("/history")
def get_voucher_history(
    db: Session = Depends(get_db), current_user: User = Depends(get_current_user)
):
    vouchers = (
        db.query(UserVoucher).filter(UserVoucher.user_id == current_user.user_id).all()
    )
    result = []
    for v in vouchers:
        template = (
            db.query(VoucherTemplate)
            .filter(VoucherTemplate.id == v.voucher_template_id)
            .first()
        )
        result.append(
            {
                "id": str(v.id),
                "code": v.code,
                "issued_at": v.issued_at,
                "expires_at": v.expires_at,
                "status": v.status,
                "title": template.title if template else None,
                "description": template.description if template else None,
                "discount_type": template.discount_type if template else None,
                "discount_value": template.discount_value if template else None,
                "partner_id": str(template.partner_id) if template else None,
            }
        )
    return result


@router.post("/redeem/{voucher_id}")
def redeem_voucher(
    voucher_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    voucher = (
        db.query(UserVoucher)
        .filter(
            UserVoucher.id == voucher_id, UserVoucher.user_id == current_user.user_id
        )
        .first()
    )
    if (
        not voucher
        or voucher.status != VoucherStatus.ACTIVE
        or voucher.expires_at < datetime.utcnow()
    ):
        raise HTTPException(
            status_code=400, detail="Voucher not valid or already redeemed/expired."
        )
    voucher.status = VoucherStatus.REDEEMED
    db.commit()
    db.refresh(voucher)
    return voucher


@router.post("/seed-demo-data")
def seed_demo_data(db: Session = Depends(get_db)):
    # Seed partners
    partners = [
        Partner(
            name="Daraz Nepal",
            description="Online shopping platform",
            logo_url="https://daraz.com/logo.png",
        ),
        Partner(
            name="Himalayan Coffee",
            description="Local coffee shop",
            logo_url="https://coffee.com/logo.png",
        ),
        Partner(
            name="WorldLink Internet",
            description="Internet provider",
            logo_url="https://worldlink.com/logo.png",
        ),
        Partner(
            name="Local Gym",
            description="Fitness center",
            logo_url="https://gym.com/logo.png",
        ),
    ]
    for p in partners:
        db.add(p)
    db.commit()
    db.refresh(partners[0])
    # Seed voucher templates
    templates = [
        VoucherTemplate(
            partner_id=partners[0].id,
            title="5% Off at Daraz",
            description="Get 5% discount on Daraz Nepal",
            discount_type="PERCENTAGE",
            discount_value=5,
            tier_required=1,
            validity_days=30,
            is_active=True,
        ),
        VoucherTemplate(
            partner_id=partners[0].id,
            title="10% Off at Daraz",
            description="Get 10% discount on Daraz Nepal",
            discount_type="PERCENTAGE",
            discount_value=10,
            tier_required=2,
            validity_days=30,
            is_active=True,
        ),
        VoucherTemplate(
            partner_id=partners[0].id,
            title="Free Shipping at Daraz",
            description="Enjoy free shipping on your next order",
            discount_type="FIXED_AMOUNT",
            discount_value=100,
            xp_required=500,
            validity_days=10,
            is_active=True,
        ),
        VoucherTemplate(
            partner_id=partners[1].id,
            title="Free Coffee",
            description="Enjoy a free coffee at Himalayan Coffee",
            discount_type="FIXED_AMOUNT",
            discount_value=200,
            tier_required=1,
            validity_days=15,
            is_active=True,
        ),
        VoucherTemplate(
            partner_id=partners[1].id,
            title="Buy 1 Get 1 Coffee",
            description="Buy one coffee, get one free",
            discount_type="FIXED_AMOUNT",
            discount_value=200,
            xp_required=1000,
            validity_days=20,
            is_active=True,
        ),
        VoucherTemplate(
            partner_id=partners[2].id,
            title="WorldLink 1 Month Discount",
            description="Get 10% off your WorldLink bill",
            discount_type="PERCENTAGE",
            discount_value=10,
            xp_required=1000,
            validity_days=30,
            is_active=True,
        ),
        VoucherTemplate(
            partner_id=partners[2].id,
            title="WorldLink Free Installation",
            description="Free installation for new WorldLink customers",
            discount_type="FIXED_AMOUNT",
            discount_value=500,
            tier_required=2,
            validity_days=30,
            is_active=True,
        ),
        VoucherTemplate(
            partner_id=partners[3].id,
            title="Gym Trial Discount",
            description="Get 50% off your first month at Local Gym",
            discount_type="PERCENTAGE",
            discount_value=50,
            xp_required=2500,
            validity_days=30,
            is_active=True,
        ),
        VoucherTemplate(
            partner_id=partners[3].id,
            title="Free Personal Training Session",
            description="Enjoy a free personal training session",
            discount_type="FIXED_AMOUNT",
            discount_value=300,
            tier_required=3,
            validity_days=15,
            is_active=True,
        ),
    ]
    for t in templates:
        db.add(t)
    db.commit()
    return {
        "partners": [p.name for p in partners],
        "templates": [t.title for t in templates],
    }
