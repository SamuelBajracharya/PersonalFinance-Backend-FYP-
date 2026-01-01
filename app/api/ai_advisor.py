
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
    current_user: User = Depends(get_current_user)
):
    """
    Get financial advice from the AI Advisor.
    """
    return await generate_advice(db, current_user.user_id, request.user_prompt)
