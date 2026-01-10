from typing import List
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session, joinedload

from app import schemas, crud
from app.utils.deps import get_db, get_current_user
from app.models import User, Reward, UserReward
from app.models.reward import RewardType
from app.services.reward_evaluation import evaluate_rewards

router = APIRouter()


@router.get("/", response_model=List[schemas.UserRewardWithUnlockStatus])
def get_all_rewards_with_status(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    evaluate_rewards(db, current_user)
    db.refresh(current_user, attribute_names=['unlocked_rewards'])

    all_rewards = db.query(Reward).all()
    user_unlocked_rewards = {ur.reward_id: ur for ur in current_user.unlocked_rewards}

    rewards_with_status = []
    for reward in all_rewards:
        unlocked = reward.id in user_unlocked_rewards
        unlocked_at = user_unlocked_rewards[reward.id].unlocked_at if unlocked else None
        rewards_with_status.append(schemas.UserRewardWithUnlockStatus(
            **reward.__dict__,
            unlocked=unlocked,
            unlocked_at=unlocked_at
        ))
    return rewards_with_status


@router.get("/me", response_model=List[schemas.UserReward])
def get_my_unlocked_rewards(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    evaluate_rewards(db, current_user)
    db.refresh(current_user, attribute_names=['unlocked_rewards'])

    unlocked_rewards_from_db = db.query(UserReward).options(
        joinedload(UserReward.reward)
    ).filter(UserReward.user_id == current_user.user_id).all()
    
    return [schemas.UserReward.from_orm(ur) for ur in unlocked_rewards_from_db]


@router.get("/recent-activity", response_model=List[schemas.RecentReward])
def get_recent_activity(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Get the 5 most recent rewards for the current user.
    """
    recent_user_rewards = crud.reward.get_user_recent_rewards(db=db, user_id=current_user.user_id)

    recent_activity = []
    for user_reward in recent_user_rewards:
        xp_gained = 0
        if user_reward.reward.reward_type == RewardType.XP:
            xp_gained = user_reward.reward.requirement_value
        
        recent_activity.append(schemas.RecentReward(
            reward_id=user_reward.reward_id,
            name=user_reward.reward.name,
            xp_gained=xp_gained,
            unlocked_at=user_reward.unlocked_at,
        ))
    return recent_activity
