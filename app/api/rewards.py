from typing import List
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session, joinedload

from app import schemas, crud
from app.utils.deps import get_db, get_current_user
from app.models import User, Reward, UserReward
from app.models.reward import RewardType
from app.models.financial_event import FinancialEvent
from app.services.reward_evaluation import evaluate_rewards

router = APIRouter()


@router.get("/", response_model=List[schemas.UserRewardWithUnlockStatus])
def get_all_rewards_with_status(
    db: Session = Depends(get_db), current_user: User = Depends(get_current_user)
):
    evaluate_rewards(db, current_user)
    db.refresh(current_user, attribute_names=["unlocked_rewards"])

    all_rewards = db.query(Reward).all()
    user_unlocked_rewards = {ur.reward_id: ur for ur in current_user.unlocked_rewards}

    rewards_with_status = []
    for reward in all_rewards:
        unlocked = reward.id in user_unlocked_rewards
        unlocked_at = user_unlocked_rewards[reward.id].unlocked_at if unlocked else None
        rewards_with_status.append(
            schemas.UserRewardWithUnlockStatus(
                **reward.__dict__, unlocked=unlocked, unlocked_at=unlocked_at
            )
        )
    return rewards_with_status


@router.get("/me", response_model=List[schemas.UserReward])
def get_my_unlocked_rewards(
    db: Session = Depends(get_db), current_user: User = Depends(get_current_user)
):
    evaluate_rewards(db, current_user)
    db.refresh(current_user, attribute_names=["unlocked_rewards"])

    unlocked_rewards_from_db = (
        db.query(UserReward)
        .options(joinedload(UserReward.reward))
        .filter(UserReward.user_id == current_user.user_id)
        .all()
    )

    return [schemas.UserReward.from_orm(ur) for ur in unlocked_rewards_from_db]


@router.get("/recent-activity", response_model=List[schemas.RecentActivity])
def get_recent_activity(
    db: Session = Depends(get_db), current_user: User = Depends(get_current_user)
):
    """
    Get the most recent XP-impacting activity for the current user.
    """
    tracked_event_types = {"budget_completed", "goal_completed", "reward_unlocked"}
    events = (
        db.query(FinancialEvent)
        .filter(
            FinancialEvent.user_id == current_user.user_id,
            FinancialEvent.event_type.in_(tracked_event_types),
        )
        .order_by(FinancialEvent.created_at.desc())
        .limit(20)
        .all()
    )

    activity_items: List[schemas.RecentActivity] = []
    for event in events:
        payload = event.payload or {}
        if event.event_type == "budget_completed":
            activity_items.append(
                schemas.RecentActivity(
                    activity_id=str(event.entity_id),
                    activity_type="budget_goal_completed",
                    name=f"Budget goal completed ({payload.get('category', 'Unknown')})",
                    xp_gained=int(payload.get("xp_gained", 10) or 0),
                    occurred_at=event.created_at,
                )
            )
        elif event.event_type == "goal_completed":
            activity_items.append(
                schemas.RecentActivity(
                    activity_id=str(event.entity_id),
                    activity_type="financial_goal_completed",
                    name=f"Financial goal completed ({payload.get('goal_type', 'Unknown')})",
                    xp_gained=int(payload.get("xp_gained", 0) or 0),
                    occurred_at=event.created_at,
                )
            )
        elif event.event_type == "reward_unlocked":
            activity_items.append(
                schemas.RecentActivity(
                    activity_id=str(event.entity_id),
                    activity_type="reward_unlocked",
                    name=payload.get("reward_name", "Reward unlocked"),
                    xp_gained=int(payload.get("xp_gained", 0) or 0),
                    occurred_at=event.created_at,
                )
            )

    return activity_items
