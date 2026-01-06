from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.utils.deps import get_db, get_current_user
from app.models.user import User
from app.schemas.what_if_scenarios import WhatIfScenario
from app.services.what_if_scenarios import get_what_if_scenarios

router = APIRouter()

@router.get(
    "/",
    response_model=list[WhatIfScenario],
    summary="Get What-If Scenarios",
    description="Analyzes current month's expenses and generates savings scenarios.",
)
def read_what_if_scenarios(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Retrieves what-if savings scenarios for the logged-in user.
    """
    return get_what_if_scenarios(db, user=current_user)

