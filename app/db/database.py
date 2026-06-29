import os
from motor.motor_asyncio import AsyncIOMotorClient
from beanie import init_beanie
from pydantic_settings import BaseSettings

from app.models.models import (
    SensorNode,
    SensorReading,
    EnvReading,
    Forecast,
    Farmer,
    Alert,
    SalinityMap
)

class Settings(BaseSettings):
    mongodb_uri: str = "mongodb://localhost:27017/coastal_saltmap"
    
    class Config:
        env_file = ".env"

settings = Settings()

async def init_db():
    # Create Motor client
    client = AsyncIOMotorClient(settings.mongodb_uri)
    
    # Safely get database, fallback to 'coastal_saltmap' if not in URI
    try:
        db = client.get_default_database()
    except Exception:
        db = client["coastal_saltmap"]
    
    # Initialize Beanie with the document models
    await init_beanie(
        database=db,
        document_models=[
            SensorNode,
            SensorReading,
            EnvReading,
            Forecast,
            Farmer,
            Alert,
            SalinityMap
        ]
    )
