from sqlalchemy.orm import Session
from app.models import User, Reward, UserReward, RewardType
from app.models.user_xp_milestone import UserXpMilestone
import uuid
import logging
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

    # Issue one voucher after reward is successfully unlocked
    from app.services.voucher_service import issue_voucher_for_tier

    issue_voucher_for_tier(
        db,
        str(user.user_id),
        getattr(reward, "tier", None),
        source_type="reward",
        source_id=str(reward.id),
    )
    # Log the reward unlock event (non-blocking)
    log_event_async(
        None,
        str(user.user_id),
        "reward_unlocked",
        "reward",
        str(reward.id),
        {
            "reward_name": reward.name,
            "tier": reward.tier,
            "requirement_value": reward.requirement_value,
            "xp_gained": 0,
        },
    )
    print(f"User {user.user_id} unlocked reward: {reward.name} Tier {reward.tier}")


def evaluate_rewards(db: Session, user: User) -> list[Reward]:
    # XP milestone voucher logic (every 500 XP)
    try:
        from app.services.voucher_service import (
            issue_voucher_for_tier,
            derive_tier_from_xp,
        )

        user_xp = user.total_xp if user.total_xp is not None else 0
        achieved_milestones = {
            m.milestone
            for m in db.query(UserXpMilestone)
            .filter(UserXpMilestone.user_id == user.user_id)
            .all()
        }
        highest_milestone = (user_xp // 500) * 500
        xp_milestones = range(500, highest_milestone + 1, 500)

        for milestone in xp_milestones:
            if milestone not in achieved_milestones:
                # Issue one voucher for each +500 milestone reached
                milestone_tier = derive_tier_from_xp(db, milestone)
                voucher = issue_voucher_for_tier(
                    db,
                    str(user.user_id),
                    milestone_tier,
                    source_type="xp_milestone",
                    source_id=str(milestone),
                )

                # Mark milestone achieved only when voucher issuance step succeeded
                if voucher is not None:
                    db.add(UserXpMilestone(user_id=user.user_id, milestone=milestone))
                    db.commit()
    except Exception as e:
        logging.exception(
            "XP milestone voucher issuance failed for user %s: %s",
            user.user_id,
            str(e),
        )
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
