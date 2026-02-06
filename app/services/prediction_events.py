from app.utils import dispatcher
from app.utils.events import BudgetCompleted, PredictionGenerated
from app.services.ai_predictions import generate_and_store_predictions_for_user
from app.services.event_logger import log_event_async


def handle_budget_completed(event: BudgetCompleted):
    db = event.db
    user_id = event.user_id
    # Generate predictions for user (idempotent)
    generate_and_store_predictions_for_user(db, user_id)
    # Optionally, log prediction generation event here if needed
    # (PredictionGenerated event will be emitted in ai_predictions service)


dispatcher.register_handler(BudgetCompleted, handle_budget_completed)
