from fastapi import APIRouter
from .auth import router as auth_router
from .bank import router as bank_router
from .analytics import router as analytics_router
from .dashboard import router as dashboard_router

api_router = APIRouter()

api_router.include_router(auth_router, prefix="/auth", tags=["auth"])
api_router.include_router(bank_router, prefix="/bank", tags=["bank"])
api_router.include_router(analytics_router, prefix="/analytics", tags=["analytics"])
api_router.include_router(dashboard_router, prefix="/dashboard", tags=["dashboard"])

__all__ = ["api_router"]
