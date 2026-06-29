from datetime import datetime, timezone
from typing import Optional, List, Dict, Any
from beanie import Document, Link, Indexed
from pydantic import BaseModel, Field

# GeoJSON Models
class GeoJSONPoint(BaseModel):
    type: str = "Point"
    coordinates: List[float]  # [longitude, latitude]

class GeoJSONLineString(BaseModel):
    type: str = "LineString"
    coordinates: List[List[float]]

# Beanie Documents
class SensorNode(Document):
    name: str
    location: GeoJSONPoint
    elevation_m: float
    distance_coast_km: float
    soil_type: str
    is_active: bool = True
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    class Settings:
        name = "sensor_nodes"
        indexes = [
            [("location", "2dsphere")]
        ]

class SensorReading(Document):
    node_id: Link[SensorNode]
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    ec_ds_m: float
    ph: float
    moisture_pct: float
    is_simulated: bool = False
    raw_payload: Dict[str, Any] = {}

    class Settings:
        name = "sensor_readings"

class EnvReading(Document):
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    rainfall_mm: float
    tidal_height_m: float
    sea_level_anomaly_m: float
    source: str
    location: GeoJSONPoint

    class Settings:
        name = "env_readings"
        indexes = [
            [("location", "2dsphere")]
        ]

class Forecast(Document):
    node_id: Link[SensorNode]
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    horizon_days: int
    ec_forecast: float
    ec_p10: float
    ec_p90: float
    risk_class: str
    model_version: str

    class Settings:
        name = "forecasts"

class Farmer(Document):
    name: str
    phone: str
    language: str = "kn"  # Default Kannada
    crop: str
    node_id: Link[SensorNode]
    is_active: bool = True
    registered_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    class Settings:
        name = "farmers"

class Alert(Document):
    farmer_id: Link[Farmer]
    node_id: Link[SensorNode]
    triggered_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    ec_value: float
    risk_class: str
    advisory_text_en: str
    advisory_text_kn: str
    channel: str
    delivered_at: Optional[datetime] = None
    status: str = "pending"

    class Settings:
        name = "alerts"

class SalinityMap(Document):
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    raster_url: str
    geojson_contours: Dict[str, Any]
    intrusion_front: GeoJSONLineString
    max_ec: float
    min_ec: float

    class Settings:
        name = "salinity_maps"
        indexes = [
            [("intrusion_front", "2dsphere")]
        ]
