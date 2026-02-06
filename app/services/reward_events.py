from app.utils import dispatcher
from app.utils.events import PredictionGenerated, RewardUnlocked
from app.models.user import User
from app.services.reward_evaluation import evaluate_rewards
from app.services.event_logger import log_event_async


def handle_prediction_generated(event: PredictionGenerated):
    db = event.db
    user_id = event.user_id
    user = db.query(User).filter(User.user_id == user_id).first()
    if not user:
        return
    new_rewards = evaluate_rewards(db, user)
    for reward in new_rewards:
        payload = {
            "reward_name": reward.name,
            "tier": reward.tier,
            "requirement_value": reward.requirement_value,
        }
        log_event_async(
            db=db,
            user_id=user_id,
            event_type="reward_unlocked",
            entity_type="reward",
            entity_id=reward.id,
            payload=payload,
        )
        dispatcher.dispatch(RewardUnlocked(db, user_id, reward.id, payload))


dispatcher.register_handler(PredictionGenerated, handle_prediction_generated)
