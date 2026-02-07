import uuid
from app.utils import dispatcher
from app.utils.events import TransactionCreated, PredictionGenerated
from app.models.bank import Transaction
from app.services.goal_progress import (
    evaluate_goals_on_transaction,
    evaluate_goals_on_prediction,
)


def handle_transaction_created(event: TransactionCreated):
    db = event.db
    try:
        transaction_id = uuid.UUID(event.transaction_id)
    except (TypeError, ValueError):
        transaction_id = event.transaction_id
    transaction = db.query(Transaction).filter(Transaction.id == transaction_id).first()
    if not transaction:
        return
    evaluate_goals_on_transaction(db, event.user_id, transaction)


def handle_prediction_generated(event: PredictionGenerated):
    evaluate_goals_on_prediction(event.db, event.user_id, event.payload or {})


dispatcher.register_handler(TransactionCreated, handle_transaction_created)
dispatcher.register_handler(PredictionGenerated, handle_prediction_generated)
