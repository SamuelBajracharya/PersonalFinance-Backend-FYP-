from sqlalchemy.orm import Session
from app.models import User, Reward, UserReward, RewardType
import uuid
from app.services.event_logger import log_event_async


def _unlock_reward(db: Session, user: User, reward: Reward):
    """
    Helper function to unlock a specific reward for a user.
    """
    user_reward = UserReward(
        id=str(uuid.uuid4()), user_id=user.user_id, reward_id=reward.id
    )
    db.add(user_reward)
    db.commit()
    db.refresh(user_reward)
    # Log the reward unlock event (non-blocking)
    log_event_async(
        db=db,
        user_id=str(user.user_id),
        event_type="reward_unlocked",
        entity_type="reward",
        entity_id=str(reward.id),
        payload={
            "reward_name": reward.name,
            "tier": reward.tier,
            "requirement_value": reward.requirement_value,
        },
    )
    print(f"User {user.user_id} unlocked reward: {reward.name} Tier {reward.tier}")


def evaluate_rewards(db: Session, user: User) -> list[Reward]:
    """
    Evaluates all potential rewards for a user and unlocks them if conditions are met.
    Returns a list of newly unlocked Reward objects.
    """
    all_rewards = db.query(Reward).all()
    unlocked_reward_ids = {ur.reward_id for ur in user.unlocked_rewards}
    newly_unlocked_rewards: list[Reward] = []

    # Get user stats
    user_xp = user.total_xp if user.total_xp is not None else 0
    user_savings = (
        user.savings if user.savings is not None else 0
    )  # Handle None for existing users
    user_completed_budgets_count = (
        user.goals_completed if user.goals_completed is not None else 0
    )

    for reward in all_rewards:
        if reward.id in unlocked_reward_ids:
            continue  # Skip already unlocked rewards

        unlocked = False
        if reward.reward_type == RewardType.XP and user_xp >= reward.requirement_value:
            unlocked = True
        elif (
            reward.reward_type == RewardType.BUDGET_GOALS
            and user_completed_budgets_count >= reward.requirement_value
        ):
            unlocked = True
        elif (
            reward.reward_type == RewardType.SAVINGS
            and user_savings >= reward.requirement_value
        ):
            unlocked = True

        if unlocked:
            _unlock_reward(db, user, reward)
            newly_unlocked_rewards.append(reward)

    return newly_unlocked_rewards
