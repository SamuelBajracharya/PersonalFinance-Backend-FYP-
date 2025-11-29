
from fastapi import APIRouter
from .auth import router as auth_router
from .bank import router as bank_router

api_router = APIRouter()

api_router.include_router(auth_router, prefix="/auth", tags=["auth"])
api_router.include_router(bank_router, prefix="/bank", tags=["bank"])

__all__ = ["api_router"]
