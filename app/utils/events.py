from typing import Callable, Dict, List, Type, Any
from collections import defaultdict


class DomainEvent:
    """Base class for all domain events."""

    pass


# --- Domain Event Types ---
class TransactionCreated(DomainEvent):
    def __init__(self, db, user_id: str, transaction_id: str, payload: dict):
        self.db = db
        self.user_id = user_id
        self.transaction_id = transaction_id
        self.payload = payload


class BudgetCompleted(DomainEvent):
    def __init__(self, db, user_id: str, budget_id: str, payload: dict):
        self.db = db
        self.user_id = user_id
        self.budget_id = budget_id
        self.payload = payload


class PredictionGenerated(DomainEvent):
    def __init__(self, db, user_id: str, prediction_id: str, payload: dict):
        self.db = db
        self.user_id = user_id
        self.prediction_id = prediction_id
        self.payload = payload


class RewardUnlocked(DomainEvent):
    def __init__(self, db, user_id: str, reward_id: str, payload: dict):
        self.db = db
        self.user_id = user_id
        self.reward_id = reward_id
        self.payload = payload


class EventDispatcher:
    def __init__(self):
        self._handlers: Dict[Type[DomainEvent], List[Callable[[DomainEvent], None]]] = (
            defaultdict(list)
        )

    def register_handler(
        self, event_type: Type[DomainEvent], handler: Callable[[DomainEvent], None]
    ):
        self._handlers[event_type].append(handler)

    def dispatch(self, event: DomainEvent):
        for handler in self._handlers[type(event)]:
            handler(event)


dispatcher = EventDispatcher()

# --- Generic event logger handler ---
from app.services.event_logger import log_event_async


def log_domain_event(event: DomainEvent):
    db = getattr(event, "db", None)
    user_id = getattr(event, "user_id", None)
    payload = getattr(event, "payload", None)
    entity_id = None
    entity_type = None
    event_type = type(event).__name__
    if hasattr(event, "transaction_id"):
        entity_id = event.transaction_id
        entity_type = "transaction"
    elif hasattr(event, "budget_id"):
        entity_id = event.budget_id
        entity_type = "budget"
    elif hasattr(event, "prediction_id"):
        entity_id = event.prediction_id
        entity_type = "prediction"
    elif hasattr(event, "reward_id"):
        entity_id = event.reward_id
        entity_type = "reward"
    if db and user_id and entity_id and entity_type and payload:
        log_event_async(
            None,
            user_id,
            event_type,
            entity_type,
            entity_id,
            payload,
        )


for evt in [TransactionCreated, BudgetCompleted, PredictionGenerated, RewardUnlocked]:
    dispatcher.register_handler(evt, log_domain_event)
