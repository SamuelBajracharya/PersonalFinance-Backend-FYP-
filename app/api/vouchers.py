from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.models.partner import Partner
from app.models.user import User
from app.models.voucher import UserVoucher, VoucherStatus, VoucherTemplate
from app.services.voucher_service import (
    generate_unique_voucher_code,
    get_user_active_vouchers,
    issue_voucher_to_user,
)
from app.utils.deps import get_current_user, get_db

router = APIRouter()


def _serialize_template(template: VoucherTemplate):
    return {
        "id": str(template.id),
        "title": template.title,
        "description": template.description,
        "discount_type": template.discount_type,
        "discount_value": template.discount_value,
        "minimum_spend": template.minimum_spend,
        "tier_required": template.tier_required,
        "xp_required": template.xp_required,
        "validity_days": template.validity_days,
        "is_active": template.is_active,
        "partner_id": str(template.partner_id),
    }


def _serialize_user_voucher(voucher: UserVoucher, template: VoucherTemplate | None):
    return {
        "id": str(voucher.id),
        "code": voucher.code,
        "issued_at": voucher.issued_at,
        "expires_at": voucher.expires_at,
        "status": voucher.status,
        "title": template.title if template else None,
        "description": template.description if template else None,
        "discount_type": template.discount_type if template else None,
        "discount_value": template.discount_value if template else None,
        "minimum_spend": template.minimum_spend if template else None,
        "tier_required": template.tier_required if template else None,
        "xp_required": template.xp_required if template else None,
        "partner_id": str(template.partner_id) if template else None,
    }


@router.get("/available")
def get_available_voucher_templates(db: Session = Depends(get_db)):
    templates = (
        db.query(VoucherTemplate).filter(VoucherTemplate.is_active == True).all()
    )
    return [_serialize_template(template) for template in templates]


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
        result.append(_serialize_user_voucher(v, template))
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
        result.append(_serialize_user_voucher(v, template))
    return result


@router.get("/all-codes")
def get_all_voucher_codes(db: Session = Depends(get_db)):
    """
    Public endpoint for dummy frontend: returns all issued voucher codes and their details.
    WARNING: Do not use in production!
    """
    vouchers = db.query(UserVoucher).all()
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
                "status": v.status,
                "expires_at": v.expires_at,
                "title": template.title if template else None,
                "description": template.description if template else None,
                "discount_type": template.discount_type if template else None,
                "discount_value": template.discount_value if template else None,
                "partner_id": str(template.partner_id) if template else None,
            }
        )
    return result


@router.get("/{voucher_id}")
def get_voucher_by_id(
    voucher_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    voucher = (
        db.query(UserVoucher)
        .filter(
            UserVoucher.id == voucher_id,
            UserVoucher.user_id == current_user.user_id,
        )
        .first()
    )

    if not voucher:
        raise HTTPException(status_code=404, detail="Voucher not found.")

    template = (
        db.query(VoucherTemplate)
        .filter(VoucherTemplate.id == voucher.voucher_template_id)
        .first()
    )

    return _serialize_user_voucher(voucher, template)


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
    template = (
        db.query(VoucherTemplate)
        .filter(VoucherTemplate.id == voucher.voucher_template_id)
        .first()
    )
    return _serialize_user_voucher(voucher, template)


@router.post("/seed-demo-data")
def seed_demo_data(db: Session = Depends(get_db)):
    partner_seed = [
        {
            "name": "Daraz Nepal",
            "description": "Online shopping platform",
            "logo_url": "https://daraz.com/logo.png",
        },
        {
            "name": "Himalayan Coffee",
            "description": "Local coffee shop",
            "logo_url": "https://coffee.com/logo.png",
        },
        {
            "name": "WorldLink Internet",
            "description": "Internet provider",
            "logo_url": "https://worldlink.com/logo.png",
        },
        {
            "name": "Local Gym",
            "description": "Fitness center",
            "logo_url": "https://gym.com/logo.png",
        },
    ]

    partners_by_name: dict[str, Partner] = {}
    created_partners = 0
    updated_partners = 0
    for partner_data in partner_seed:
        existing_partner = (
            db.query(Partner).filter(Partner.name == partner_data["name"]).first()
        )
        if existing_partner:
            existing_partner.description = partner_data["description"]
            existing_partner.logo_url = partner_data["logo_url"]
            db.add(existing_partner)
            partners_by_name[partner_data["name"]] = existing_partner
            updated_partners += 1
        else:
            new_partner = Partner(**partner_data)
            db.add(new_partner)
            db.flush()
            partners_by_name[partner_data["name"]] = new_partner
            created_partners += 1

    template_seed = [
        {
            "partner_name": "Daraz Nepal",
            "title": "5% Off at Daraz",
            "description": "Get 5% discount on Daraz Nepal",
            "discount_type": "PERCENTAGE",
            "discount_value": 5,
            "tier_required": 1,
            "xp_required": 500,
            "validity_days": 30,
            "is_active": True,
        },
        {
            "partner_name": "Daraz Nepal",
            "title": "10% Off at Daraz",
            "description": "Get 10% discount on Daraz Nepal",
            "discount_type": "PERCENTAGE",
            "discount_value": 10,
            "tier_required": 2,
            "xp_required": 1000,
            "validity_days": 30,
            "is_active": True,
        },
        {
            "partner_name": "Daraz Nepal",
            "title": "Free Shipping at Daraz",
            "description": "Enjoy free shipping on your next order",
            "discount_type": "FIXED_AMOUNT",
            "discount_value": 100,
            "tier_required": 1,
            "xp_required": 500,
            "validity_days": 10,
            "is_active": True,
        },
        {
            "partner_name": "Himalayan Coffee",
            "title": "Free Coffee",
            "description": "Enjoy a free coffee at Himalayan Coffee",
            "discount_type": "FIXED_AMOUNT",
            "discount_value": 200,
            "tier_required": 1,
            "xp_required": 500,
            "validity_days": 15,
            "is_active": True,
        },
        {
            "partner_name": "Himalayan Coffee",
            "title": "Buy 1 Get 1 Coffee",
            "description": "Buy one coffee, get one free",
            "discount_type": "FIXED_AMOUNT",
            "discount_value": 200,
            "tier_required": 2,
            "xp_required": 1000,
            "validity_days": 20,
            "is_active": True,
        },
        {
            "partner_name": "WorldLink Internet",
            "title": "WorldLink 1 Month Discount",
            "description": "Get 10% off your WorldLink bill",
            "discount_type": "PERCENTAGE",
            "discount_value": 10,
            "tier_required": 2,
            "xp_required": 1000,
            "validity_days": 30,
            "is_active": True,
        },
        {
            "partner_name": "WorldLink Internet",
            "title": "WorldLink Free Installation",
            "description": "Free installation for new WorldLink customers",
            "discount_type": "FIXED_AMOUNT",
            "discount_value": 500,
            "tier_required": 3,
            "xp_required": 1500,
            "validity_days": 30,
            "is_active": True,
        },
        {
            "partner_name": "Local Gym",
            "title": "Gym Trial Discount",
            "description": "Get 50% off your first month at Local Gym",
            "discount_type": "PERCENTAGE",
            "discount_value": 50,
            "tier_required": 4,
            "xp_required": 2500,
            "validity_days": 30,
            "is_active": True,
        },
        {
            "partner_name": "Local Gym",
            "title": "Free Personal Training Session",
            "description": "Enjoy a free personal training session",
            "discount_type": "FIXED_AMOUNT",
            "discount_value": 300,
            "tier_required": 3,
            "xp_required": 1500,
            "validity_days": 15,
            "is_active": True,
        },
    ]

    created_templates = 0
    updated_templates = 0
    serialized_templates = []
    for template_data in template_seed:
        partner = partners_by_name.get(template_data["partner_name"])
        if not partner:
            continue

        existing_template = (
            db.query(VoucherTemplate)
            .filter(VoucherTemplate.title == template_data["title"])
            .first()
        )

        payload = {
            "partner_id": partner.id,
            "title": template_data["title"],
            "description": template_data["description"],
            "discount_type": template_data["discount_type"],
            "discount_value": template_data["discount_value"],
            "tier_required": template_data["tier_required"],
            "xp_required": template_data["xp_required"],
            "validity_days": template_data["validity_days"],
            "is_active": template_data["is_active"],
        }

        if existing_template:
            existing_template.partner_id = payload["partner_id"]
            existing_template.description = payload["description"]
            existing_template.discount_type = payload["discount_type"]
            existing_template.discount_value = payload["discount_value"]
            existing_template.tier_required = payload["tier_required"]
            existing_template.xp_required = payload["xp_required"]
            existing_template.validity_days = payload["validity_days"]
            existing_template.is_active = payload["is_active"]
            db.add(existing_template)
            serialized_templates.append(_serialize_template(existing_template))
            updated_templates += 1
        else:
            new_template = VoucherTemplate(**payload)
            db.add(new_template)
            db.flush()
            serialized_templates.append(_serialize_template(new_template))
            created_templates += 1

    db.commit()
    return {
        "partners": {
            "created": created_partners,
            "updated": updated_partners,
            "items": list(partners_by_name.keys()),
        },
        "templates": {
            "created": created_templates,
            "updated": updated_templates,
            "items": serialized_templates,
        },
    }
