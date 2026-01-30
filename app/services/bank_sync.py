import asyncio
import logging
from datetime import datetime
from decimal import Decimal

import httpx
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from app.models.bank import BankAccount, Transaction
from app.models.user import User

EXTERNAL_BANK_API_BASE_URL = "https://koshconnect.onrender.com"

# Set up logging
logger = logging.getLogger(__name__)


async def login_and_sync_all_accounts(
    user_id: str, username: str, password: str, db: Session
):
    """
    Logs into KoshConnect, creates BankAccount rows for each synced account,
    and fetches all transactions for each account.
    """
    summary = {
        "status": "failed",
        "message": "Login failed or no accounts found.",
        "synced_accounts": [],
    }

    try:
        async with httpx.AsyncClient() as client:
            try:
                login_response = await client.post(
                    f"{EXTERNAL_BANK_API_BASE_URL}/token",
                    data={"username": username, "password": password},
                )
                login_response.raise_for_status()
                login_data = login_response.json()
            except httpx.HTTPStatusError as e:
                logger.error(f"HTTP error during KoshConnect login: {e.response.status_code} - {e.response.text}")
                summary["message"] = f"KoshConnect login failed: {e.response.status_code}"
                return summary
            except httpx.RequestError as e:
                logger.error(f"Network error during KoshConnect login: {e}")
                summary["message"] = f"Network error during KoshConnect login: {e}"
                return summary
            except Exception as e:
                logger.error(f"Unexpected error during KoshConnect login: {e}", exc_info=True)
                summary["message"] = f"Login failed: {e}"
                return summary

            accounts = login_data.get("accounts")
            bank_token = login_data.get("access_token")

            if not accounts or not bank_token:
                summary["message"] = "Login succeeded, but no accounts returned."
                return summary

            summary["synced_accounts"] = accounts
            summary["bank_token"] = bank_token

            headers = {"Authorization": f"Bearer {bank_token}"}
            synced_accounts_result = []

            # Process each account
            for account in accounts:
                external_account_id = account["account_id"]

                # Create BankAccount if not exists
                local_account = (
                    db.query(BankAccount)
                    .filter(BankAccount.external_account_id == external_account_id)
                    .first()
                )

                if not local_account:
                    try:
                        local_account = BankAccount(
                            external_account_id=external_account_id,
                            user_id=user_id,
                            bank_name=account["bank_name"],
                            account_number_masked=account["account_number_masked"],
                            account_type=account["account_type"],
                            balance=Decimal(str(account["balance"])),
                            is_active=True,
                        )
                        db.add(local_account)
                        db.commit()
                        db.refresh(local_account)
                    except IntegrityError as e:
                        db.rollback()
                        logger.warning(f"Integrity error creating bank account {external_account_id}, likely duplicate. Fetching existing. Error: {e}")
                        local_account = (
                            db.query(BankAccount)
                            .filter(BankAccount.external_account_id == external_account_id)
                            .first()
                        )
                        if not local_account: # Should not happen if IntegrityError was due to duplicate
                            logger.error(f"Failed to retrieve existing bank account after IntegrityError for {external_account_id}")
                            raise e # Re-raise if we still can't find it
                    except Exception as e:
                        db.rollback()
                        logger.error(f"Error creating bank account {external_account_id}: {e}", exc_info=True)
                        raise e # Re-raise the exception
                else:
                    # If account is inactive, re-activate it.
                    if not local_account.is_active:
                        local_account.is_active = True
                        db.commit()
                        db.refresh(local_account)

                    # Update balance if changed
                    if local_account.balance != Decimal(str(account["balance"])):
                        local_account.balance = Decimal(str(account["balance"]))
                        db.commit()
                        db.refresh(local_account)
                
                # Skip transaction sync for inactive accounts
                if not local_account.is_active:
                    synced_accounts_result.append(
                        {
                            "external_account_id": external_account_id,
                            "local_account_id": local_account.id,
                            "new_transactions": 0, # No new transactions synced
                            "status": "inactive_skipped"
                        }
                    )
                    continue

                # Fetch transactions from KoshConnect
                try:
                    tx_response = await client.get(
                        f"{EXTERNAL_BANK_API_BASE_URL}/accounts/{external_account_id}/transactions",
                        headers=headers,
                    )
                    tx_response.raise_for_status()
                    transactions_data = tx_response.json()
                except httpx.HTTPStatusError as e:
                    logger.error(f"HTTP error fetching transactions for {external_account_id}: {e.response.status_code} - {e.response.text}")
                    transactions_data = [] # Continue without transactions for this account
                except httpx.RequestError as e:
                    logger.error(f"Network error fetching transactions for {external_account_id}: {e}")
                    transactions_data = [] # Continue without transactions for this account
                except Exception as e:
                    logger.error(f"Unexpected error fetching transactions for {external_account_id}: {e}", exc_info=True)
                    transactions_data = [] # Continue without transactions for this account


                new_transactions_count = 0
                for tx in transactions_data:
                    existing_tx = (
                        db.query(Transaction)
                        .filter(Transaction.external_transaction_id == tx["transaction_id"])
                        .first()
                    )
                    if existing_tx:
                        continue
                    try:
                        new_tx = Transaction(
                            external_transaction_id=tx["transaction_id"],
                            user_id=user_id,
                            account_id=local_account.id,
                            source="BANK",
                            date=datetime.fromisoformat(tx["date"].replace("Z", "+00:00")),
                            amount=Decimal(str(tx["amount"])),
                            currency=tx["currency"],
                            type=tx["type"],
                            status=tx["status"],
                            description=tx.get("description"),
                            merchant=tx.get("merchant"),
                            category=tx.get("category"),
                        )
                        db.add(new_tx)
                        db.commit()
                        db.refresh(new_tx)
                        new_transactions_count += 1
                    except Exception as e:
                        db.rollback()
                        logger.error(f"Failed to add transaction {tx['transaction_id']}: {e}", exc_info=True)
                        # Decide if you want to re-raise or just log and continue
                        # For now, we log and continue to process other transactions
                        # If a single transaction failure should halt the whole sync, re-raise here.


                synced_accounts_result.append(
                    {
                        "external_account_id": external_account_id,
                        "local_account_id": local_account.id,
                        "new_transactions": new_transactions_count,
                        "status": "synced"
                    }
                )

            summary["status"] = "success"
            summary["message"] = "All accounts and transactions synced successfully."
            summary["synced_accounts_detail"] = synced_accounts_result
            return summary

    except Exception as e:
        # Catch any unexpected error that might escape above try/except blocks
        logger.critical(f"Unhandled critical error in login_and_sync_all_accounts: {e}", exc_info=True)
        summary["message"] = f"An unexpected error occurred during bank synchronization: {e}"
        # Re-raise the exception to ensure FastAPI catches it and provides a traceback
        raise e
