from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.schemas.ai_advisor import AIAdvisorRequest, AIAdvisorResponse
from app.services.ai_advisor import generate_advice
from app.utils.deps import get_db, get_current_user
from app.models.user import User

router = APIRouter()


@router.post("/advisor", response_model=AIAdvisorResponse)
async def get_financial_advice(
    request: AIAdvisorRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Get financial advice from the AI Advisor.
    """
    # Fetch sync status
    from app.crud.bank_sync_status import get_sync_status

    sync_status = get_sync_status(db, current_user.user_id)
    is_data_fresh = False
    last_successful_sync = None
    last_attempted_sync = None
    sync_status_value = None
    failure_reason = None
    if sync_status:
        last_successful_sync = sync_status.last_successful_sync
        last_attempted_sync = sync_status.last_attempted_sync
        sync_status_value = sync_status.sync_status
        failure_reason = sync_status.failure_reason
        from datetime import date

        is_data_fresh = (
            last_successful_sync is not None
            and last_successful_sync.date() == date.today()
        )
    resp = await generate_advice(db, current_user.user_id, request.user_prompt)
    resp.is_data_fresh = is_data_fresh
    resp.last_successful_sync = last_successful_sync
    resp.last_attempted_sync = last_attempted_sync
    resp.sync_status = sync_status_value
    resp.failure_reason = failure_reason
    return resp
