
from pydantic import BaseModel
from datetime import datetime
from typing import Optional
from app.models.reward import RewardType

class RewardBase(BaseModel):
    name: str
    tier: int
    reward_type: RewardType
    requirement_value: int

class RewardCreate(RewardBase):
    pass

class Reward(RewardBase):
    id: str
    created_at: datetime

    class Config:
        from_attributes = True

class UserRewardBase(BaseModel):
    user_id: str
    reward_id: str

class UserRewardCreate(UserRewardBase):
    pass

class UserReward(UserRewardBase):
    id: str
    unlocked_at: datetime
    reward: Reward # This will allow nesting the reward details

    class Config:
        from_attributes = True

class UserRewardWithUnlockStatus(Reward):
    unlocked: bool = False
    unlocked_at: Optional[datetime] = None


class RecentReward(BaseModel):
    reward_id: str
    name: str
    xp_gained: int
    unlocked_at: datetime
