from app.db.session import SessionLocal
from app.services.ai_predictions import generate_and_store_predictions_for_user
from app.crud.budget import update_completed_budgets_for_user
from app.models.user import User


def trigger_predictions_and_budget_evaluation(user_id: str):
    db = SessionLocal()
    try:
        # Generate and store predictions (idempotent)
        generate_and_store_predictions_for_user(db, user_id)
        # Update completed budgets and evaluate rewards
        update_completed_budgets_for_user(db, user_id)
    finally:
        db.close()
