"""
Example Event Flow: transaction.created → prediction.generated

1. A new transaction is synced (bank_sync.py):
   - Emits TransactionCreated event.
2. budget_events.py listens for TransactionCreated:
   - Checks if any budget is completed, emits BudgetCompleted if so.
3. prediction_events.py listens for BudgetCompleted:
   - Triggers prediction generation, emits PredictionGenerated.
4. reward_events.py listens for PredictionGenerated:
   - Evaluates and unlocks rewards, emits RewardUnlocked.
5. All events are also logged to FinancialEvent timeline by a generic handler.

Reduced Coupling Explanation:
- Services do not import or call each other directly.
- Each service emits events and registers handlers for events it cares about.
- Adding new features or listeners does not require modifying existing services.
- The dispatcher enables easy extension (e.g., add async, queue, or external broker later).
- This architecture supports open/closed principle and improves maintainability.
"""
