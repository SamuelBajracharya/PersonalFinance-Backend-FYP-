from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session, joinedload

from app import schemas
from app.utils.deps import get_db, get_current_user # Updated import
from app.models import User, Reward, UserReward
from app.services.reward_evaluation import evaluate_rewards

router = APIRouter()

@router.get("/", response_model=List[schemas.UserRewardWithUnlockStatus])
def get_all_rewards_with_status(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    # Ensure user's rewards are up-to-date
    evaluate_rewards(db, current_user)
    # Refresh the user object to get the latest unlocked_rewards, 
    # especially important if evaluate_rewards modified the relationship within the same session
    db.refresh(current_user, attribute_names=['unlocked_rewards']) 

    all_rewards = db.query(Reward).all()
    user_unlocked_rewards = {ur.reward_id: ur for ur in current_user.unlocked_rewards}

    rewards_with_status = []
    for reward in all_rewards:
        if reward.id in user_unlocked_rewards:
            user_reward = user_unlocked_rewards[reward.id]
            rewards_with_status.append(schemas.UserRewardWithUnlockStatus(
                **reward.__dict__,
                unlocked=True,
                unlocked_at=user_reward.unlocked_at
            ))
        else:
            rewards_with_status.append(schemas.UserRewardWithUnlockStatus(
                **reward.__dict__,
                unlocked=False,
                unlocked_at=None
            ))
    return rewards_with_status

@router.get("/me", response_model=List[schemas.UserReward])
def get_my_unlocked_rewards(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    # Ensure user's rewards are up-to-date
    evaluate_rewards(db, current_user)
    # Refresh the user object to get the latest unlocked_rewards
    db.refresh(current_user, attribute_names=['unlocked_rewards']) 

    # Eager load the Reward details for each UserReward object
    # This avoids N+1 queries and ensures reward details are available
    unlocked_rewards_from_db = db.query(UserReward).options(joinedload(UserReward.reward)).filter(
        UserReward.user_id == current_user.user_id
    ).all()
    
    return [schemas.UserReward.from_orm(ur) for ur in unlocked_rewards_from_db]
