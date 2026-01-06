from fastapi import APIRouter
from .auth import router as auth_router
from .bank import router as bank_router
from .analytics import router as analytics_router
from .dashboard import router as dashboard_router
from .ai_advisor import router as ai_advisor_router
from .budget import router as budget_router
from .what_if_scenarios import router as what_if_scenarios_router

api_router = APIRouter()

api_router.include_router(auth_router, prefix="/auth", tags=["auth"])
api_router.include_router(bank_router, prefix="/bank", tags=["bank"])
api_router.include_router(analytics_router, prefix="/analytics", tags=["analytics"])
api_router.include_router(dashboard_router, prefix="/dashboard", tags=["dashboard"])
api_router.include_router(ai_advisor_router, prefix="/ai", tags=["ai"])
api_router.include_router(budget_router, prefix="/budgets", tags=["budgets"])
api_router.include_router(what_if_scenarios_router, prefix="/what-if-scenarios", tags=["what-if-scenarios"])

__all__ = ["api_router"]