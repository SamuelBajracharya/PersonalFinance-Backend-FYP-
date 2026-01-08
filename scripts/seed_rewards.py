import os
from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.db.base import Base
from app.models import Reward, RewardType
import uuid

# Load environment variables from .env file
load_dotenv()

# Database setup
DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise ValueError("DATABASE_URL environment variable is not set.")

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def seed_rewards():
    db = SessionLocal()
    try:
        rewards_to_seed = []

        # XP-Based Rewards
        for i in range(1, 11):
            rewards_to_seed.append(Reward(
                id=str(uuid.uuid4()),
                name="Budget Brilliance",
                tier=i,
                reward_type=RewardType.XP,
                requirement_value=i * 1000
            ))

        # Budget Goals Completion Rewards
        for i in range(1, 11):
            rewards_to_seed.append(Reward(
                id=str(uuid.uuid4()),
                name="Budget Goal-Getter",
                tier=i,
                reward_type=RewardType.BUDGET_GOALS,
                requirement_value=i * 10
            ))

        # Savings-Based Rewards
        for i in range(1, 11):
            rewards_to_seed.append(Reward(
                id=str(uuid.uuid4()),
                name="Grand Saver",
                tier=i,
                reward_type=RewardType.SAVINGS,
                requirement_value=i * 1000
            ))

        for reward_data in rewards_to_seed:
            existing_reward = db.query(Reward).filter(
                Reward.name == reward_data.name,
                Reward.tier == reward_data.tier,
                Reward.reward_type == reward_data.reward_type
            ).first()

            if not existing_reward:
                db.add(reward_data)
                print(f"Added reward: {reward_data.name} Tier {reward_data.tier} ({reward_data.reward_type.value})")
            else:
                print(f"Reward already exists: {reward_data.name} Tier {reward_data.tier} ({reward_data.reward_type.value})")
        
        db.commit()
    except Exception as e:
        db.rollback()
        raise e
    finally:
        db.close()

if __name__ == "__main__":
    print("Seeding rewards table...")
    seed_rewards()
    print("Rewards seeding complete.")
