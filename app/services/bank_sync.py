import asyncio
from datetime import datetime
from decimal import Decimal

import httpx
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from app.models.bank import BankAccount, Transaction
from app.models.user import User

EXTERNAL_BANK_API_BASE_URL = "https://koshconnect.onrender.com"


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

    async with httpx.AsyncClient() as client:
        try:
            login_response = await client.post(
                f"{EXTERNAL_BANK_API_BASE_URL}/token",
                data={"username": username, "password": password},
            )
            login_response.raise_for_status()
            login_data = login_response.json()
        except Exception as e:
            summary["message"] = f"Login failed: {e}"
            print(summary["message"])
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
                    )
                    db.add(local_account)
                    db.commit()
                    db.refresh(local_account)
                except IntegrityError:
                    db.rollback()
                    local_account = (
                        db.query(BankAccount)
                        .filter(BankAccount.external_account_id == external_account_id)
                        .first()
                    )
                except Exception as e:
                    print(f"Error creating bank account {external_account_id}: {e}")
                    continue
            else:
                # Update balance if changed
                if local_account.balance != Decimal(str(account["balance"])):
                    local_account.balance = Decimal(str(account["balance"]))
                    db.commit()
                    db.refresh(local_account)

            # Fetch transactions from KoshConnect
            try:
                tx_response = await client.get(
                    f"{EXTERNAL_BANK_API_BASE_URL}/accounts/{external_account_id}/transactions",
                    headers=headers,
                )
                tx_response.raise_for_status()
                transactions_data = tx_response.json()
            except Exception as e:
                print(f"Failed to fetch transactions for {external_account_id}: {e}")
                transactions_data = []

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
                    print(f"Failed to add transaction {tx['transaction_id']}: {e}")

            synced_accounts_result.append(
                {
                    "external_account_id": external_account_id,
                    "local_account_id": local_account.id,
                    "new_transactions": new_transactions_count,
                }
            )

        summary["status"] = "success"
        summary["message"] = "All accounts and transactions synced successfully."
        summary["synced_accounts_detail"] = synced_accounts_result
        return summary
