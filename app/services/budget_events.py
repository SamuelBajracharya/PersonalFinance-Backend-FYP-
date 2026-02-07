from app.utils import dispatcher
from app.utils.events import TransactionCreated, BudgetCompleted
from app.crud.budget import get_budgets_by_user, evaluate_budget_completion
from app.models.user import User
from app.models.budget import Budget
from app.services.event_logger import log_event_async


def handle_transaction_created(event: TransactionCreated):
    db = event.db
    user_id = event.user_id
    user = db.query(User).filter(User.user_id == user_id).first()
    if not user:
        return
    budgets = get_budgets_by_user(db, user_id)
    for budget in budgets:
        if not budget.is_completed:
            completed = evaluate_budget_completion(db, budget, user)
            if completed:
                budget.is_completed = True
                db.add(budget)
                db.commit()
                db.refresh(budget)
                payload = {
                    "category": budget.category,
                    "budget_amount": float(budget.budget_amount),
                    "remaining_budget": float(budget.remaining_budget),
                }
                log_event_async(
                    db,
                    user_id,
                    "budget_completed",
                    "budget",
                    budget.id,
                    payload,
                )
                dispatcher.dispatch(BudgetCompleted(db, user_id, budget.id, payload))


dispatcher.register_handler(TransactionCreated, handle_transaction_created)
