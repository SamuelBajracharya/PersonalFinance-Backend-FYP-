from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api import api_router
import asyncio
import app.services.budget_events  # Import event handler modules to ensure registration
import app.services.prediction_events
import app.services.reward_events
from app.services.background_tasks import run_daily_bank_sync_loop
from app.db import Base, engine
import app.models  # Import all models to register them with Base.metadata

# Create database tables
Base.metadata.create_all(bind=engine)

# Initialize FastAPI app
app = FastAPI()
daily_sync_task = None

# CORS configuration
origins = [
    "http://localhost:3000",
    "http://localhost:5173",
    "http://127.0.0.1:3000",
    "http://127.0.0.1:5500",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include your API routes
app.include_router(api_router, prefix="/api/v1")


@app.on_event("startup")
async def start_daily_sync_worker():
    global daily_sync_task
    if daily_sync_task is None:
        daily_sync_task = asyncio.create_task(run_daily_bank_sync_loop(60))


@app.on_event("shutdown")
async def stop_daily_sync_worker():
    global daily_sync_task
    if daily_sync_task is not None:
        daily_sync_task.cancel()
        try:
            await daily_sync_task
        except asyncio.CancelledError:
            pass
        daily_sync_task = None
