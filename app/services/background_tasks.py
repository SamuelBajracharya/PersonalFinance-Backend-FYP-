from app.db.session import SessionLocal
from app.services.ai_predictions import generate_and_store_predictions_for_user
from app.crud.budget import update_completed_budgets_for_user
from app.models.user import User
from app.models.bank import BankAccount
from app.models.bank_sync_status import BankSyncStatus
from app.services.bank_sync import login_and_sync_all_accounts
from app.services.bank_sync_status import record_bank_sync_attempt
from datetime import datetime, timezone
import asyncio
import logging


logger = logging.getLogger(__name__)


def trigger_predictions_and_budget_evaluation(user_id: str):
    db = SessionLocal()
    try:
        # Generate and store predictions (idempotent)
        generate_and_store_predictions_for_user(db, user_id)
        # Update completed budgets and evaluate rewards
        update_completed_budgets_for_user(db, user_id)
    finally:
        db.close()


def _is_synced_today(last_successful_sync) -> bool:
    if last_successful_sync is None:
        return False

    now_utc = datetime.now(timezone.utc)
    if last_successful_sync.tzinfo is None:
        return last_successful_sync.date() == now_utc.date()
    return last_successful_sync.astimezone(timezone.utc).date() == now_utc.date()


async def run_daily_bank_sync_once():
    """Sync users with active token-backed bank accounts if they haven't synced successfully today."""
    db = SessionLocal()
    try:
        candidates = (
            db.query(BankAccount.user_id, BankAccount.bank_token)
            .filter(
                BankAccount.is_active == True,
                BankAccount.bank_token != None,
            )
            .distinct(BankAccount.user_id)
            .all()
        )

        for user_id, bank_token in candidates:
            if not bank_token:
                continue

            sync_status = (
                db.query(BankSyncStatus)
                .filter(BankSyncStatus.user_id == user_id)
                .first()
            )
            if sync_status and _is_synced_today(sync_status.last_successful_sync):
                continue

            success = False
            failure_reason = None
            try:
                summary = await login_and_sync_all_accounts(
                    user_id=user_id,
                    username=None,
                    password=None,
                    db=db,
                    bank_token=bank_token,
                )
                success = summary.get("status") == "success"
                if not success:
                    failure_reason = summary.get("message") or "Daily sync failed"
            except Exception as e:
                failure_reason = str(e)
                logger.exception("Daily bank sync failed for user_id=%s", user_id)
            finally:
                record_bank_sync_attempt(db, user_id, success, failure_reason)
    finally:
        db.close()


async def run_daily_bank_sync_loop(interval_minutes: int = 60):
    """Periodic loop that guarantees at least one daily bank sync attempt per eligible user."""
    while True:
        try:
            await run_daily_bank_sync_once()
        except Exception:
            logger.exception("Unexpected error in daily bank sync loop")

        await asyncio.sleep(max(1, interval_minutes) * 60)
