
import httpx
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
import uuid
from datetime import datetime
from decimal import Decimal

from app.models.bank import BankAccount, Transaction
from app.models.user import User # Assuming User model is needed for user_id type
from app.crud.bank import get_bank_account, create_transaction, get_transactions_by_account
from app.db.base import Base # For Base.metadata.create_all if needed for testing

EXTERNAL_BANK_API_BASE_URL = "https://koshconnect-production.up.railway.app"

async def fetch_and_sync_bank_data(user_id: str, target_account_id: str, db: Session):
    print(f"Starting bank data sync for user {user_id} and account {target_account_id}")
    summary = {
        "status": "failed",
        "message": "",
        "new_transactions": 0,
        "updated_balance": False,
        "account_created": False,
    }

    async with httpx.AsyncClient() as client:
        # 1. Fetch Account Details
        try:
            print("Fetching account details from external API...")
            account_response = await client.get(f"{EXTERNAL_BANK_API_BASE_URL}/accounts/{target_account_id}")
            account_response.raise_for_status()
            external_account_data = account_response.json()
            print("Successfully fetched account details.")
        except httpx.HTTPStatusError as e:
            summary["message"] = f"HTTP error fetching account {target_account_id}: {e}"
            print(f"ERROR: {summary['message']}")
            return summary
        except httpx.RequestError as e:
            summary["message"] = f"Network error fetching account {target_account_id}: {e}"
            print(f"ERROR: {summary['message']}")
            return summary
        except Exception as e:
            summary["message"] = f"Unexpected error fetching account {target_account_id}: {e}"
            print(f"ERROR: {summary['message']}")
            return summary

        # Find or Create/Update BankAccount
        print("Looking for local bank account...")
        local_bank_account = db.query(BankAccount).filter(
            BankAccount.external_account_id == external_account_data["account_id"]
        ).first()

        if not local_bank_account:
            try:
                print("Local bank account not found. Creating a new one...")
                local_bank_account = BankAccount(
                    external_account_id=external_account_data["account_id"],
                    user_id=user_id,
                    bank_name=external_account_data["bank_name"],
                    account_number_masked=external_account_data["account_number_masked"],
                    account_type=external_account_data["account_type"],
                    balance=Decimal(str(external_account_data["balance"])),
                )
                db.add(local_bank_account)
                db.commit()
                db.refresh(local_bank_account)
                summary["account_created"] = True
                print("Successfully created new local bank account.")
            except IntegrityError:
                db.rollback()
                print("IntegrityError creating account, rolling back and trying to fetch again.")
                local_bank_account = db.query(BankAccount).filter(
                    BankAccount.external_account_id == external_account_data["account_id"]
                ).first()
                if not local_bank_account:
                    summary["message"] = "Failed to create bank account due to integrity error and subsequent lookup failed."
                    print(f"ERROR: {summary['message']}")
                    return summary
            except Exception as e:
                db.rollback()
                summary["message"] = f"Error creating bank account: {e}"
                print(f"ERROR: {summary['message']}")
                return summary
        else:
            print("Found local bank account. Checking for balance update...")
            if local_bank_account.balance != Decimal(str(external_account_data["balance"])):
                local_bank_account.balance = Decimal(str(external_account_data["balance"]))
                db.add(local_bank_account)
                db.commit()
                db.refresh(local_bank_account)
                summary["updated_balance"] = True
                print("Updated local bank account balance.")
            else:
                print("Local bank account balance is already up to date.")

        # 2. Fetch Transactions
        try:
            print("Fetching transactions from external API...")
            transactions_response = await client.get(f"{EXTERNAL_BANK_API_BASE_URL}/accounts/{target_account_id}/transactions")
            transactions_response.raise_for_status()
            external_transactions_data = transactions_response.json()
            print("Successfully fetched transactions.")
        except httpx.HTTPStatusError as e:
            summary["message"] = f"HTTP error fetching transactions for account {target_account_id}: {e}"
            print(f"ERROR: {summary['message']}")
            return summary
        except httpx.RequestError as e:
            summary["message"] = f"Network error fetching transactions for account {target_account_id}: {e}"
            print(f"ERROR: {summary['message']}")
            return summary
        except Exception as e:
            summary["message"] = f"Unexpected error fetching transactions for account {target_account_id}: {e}"
            print(f"ERROR: {summary['message']}")
            return summary

        # Sync Transactions
        print("Syncing transactions...")
        new_transactions_count = 0
        for ext_transaction in external_transactions_data:
            existing_transaction = db.query(Transaction).filter(
                Transaction.external_transaction_id == ext_transaction["transaction_id"]
            ).first()

            if not existing_transaction:
                try:
                    print(f"Creating new transaction {ext_transaction['transaction_id']}")
                    new_transaction = Transaction(
                        external_transaction_id=ext_transaction["transaction_id"],
                        user_id=user_id,
                        account_id=local_bank_account.id,
                        source="BANK",
                        date=datetime.fromisoformat(ext_transaction["date"].replace("Z", "+00:00")),
                        amount=Decimal(str(ext_transaction["amount"])),
                        currency=ext_transaction["currency"],
                        type=ext_transaction["type"],
                        status=ext_transaction["status"],
                        description=ext_transaction.get("description"),
                        merchant=ext_transaction.get("merchant"),
                        category=ext_transaction.get("category"),
                    )
                    db.add(new_transaction)
                    db.commit()
                    db.refresh(new_transaction)
                    new_transactions_count += 1
                except IntegrityError:
                    db.rollback()
                    print(f"IntegrityError on transaction {ext_transaction['transaction_id']}, rolling back.")
                except Exception as e:
                    db.rollback()
                    print(f"Error adding transaction {ext_transaction.get('transaction_id')}: {e}")

    summary["new_transactions"] = new_transactions_count
    summary["status"] = "success"
    summary["message"] = "Bank data synced successfully."
    print("Bank data sync finished successfully.")
    return summary
