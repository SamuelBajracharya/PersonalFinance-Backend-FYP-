from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional
from app.models.bank_sync_status import SyncStatusEnum


class BankSyncStatusSchema(BaseModel):
    user_id: str
    last_successful_sync: Optional[datetime] = None
    last_attempted_sync: Optional[datetime] = None
    last_transaction_fetched_at: Optional[datetime] = None
    sync_status: Optional[SyncStatusEnum] = None
    failure_reason: Optional[str] = None

    class Config:
        from_attributes = True
