from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import logging

from app.db.database import init_db
from app.scheduler import setup_scheduler
from app.routers import api_v1  # IMPORT ROUTER

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

scheduler = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Initializing Database...")
    await init_db()
    
    logger.info("Starting Background Scheduler...")
    global scheduler
    scheduler = setup_scheduler()
    scheduler.start()
    
    yield
    
    logger.info("Shutting down Background Scheduler...")
    if scheduler:
        scheduler.shutdown()

app = FastAPI(
    title="Coastal SaltMAP API",
    lifespan=lifespan
)

# --- Add this CORS block ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # In production, change this to your frontend URL
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
# ---------------------------
# MOUNT ROUTER HERE
app.include_router(api_v1.router)

@app.get("/")
async def root():
    return {"message": "SaltMAP API is running."}
