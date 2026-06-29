from typing import List, Optional
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Query, status
from beanie import PydanticObjectId

from app.dependencies import get_api_key
from app.models.models import (
    SensorNode, SensorReading, Forecast, SalinityMap, Alert, Farmer
)

router = APIRouter(
    prefix="/api/v1",
    tags=["Government Backend v1"],
    dependencies=[Depends(get_api_key)] # Secures all endpoints in this router
)

# ==========================================
# Nodes & Readings
# ==========================================

@router.get("/nodes")
async def get_nodes():
    """API-01: List all sensor nodes."""
    nodes = await SensorNode.find_all().to_list()
    # In a real scenario, we might join the latest reading here, 
    # but returning the node metadata is standard.
    return {"nodes": nodes}

@router.get("/nodes/{id}/readings")
async def get_node_readings(
    id: PydanticObjectId, 
    from_date: Optional[datetime] = None, 
    to_date: Optional[datetime] = None
):
    """API-02: Time-series readings for a node with optional date filters."""
    query = SensorReading.find(SensorReading.node_id == id)
    
    if from_date:
        query = query.find(SensorReading.timestamp >= from_date)
    if to_date:
        query = query.find(SensorReading.timestamp <= to_date)
        
    readings = await query.sort("-timestamp").to_list()
    return {"node_id": str(id), "readings": readings}


# ==========================================
# Spatial Mapping
# ==========================================

@router.get("/map/heatmap")
async def get_salinity_heatmap():
    """API-03: Return the geojson_contours from the latest SalinityMaps document."""
    latest_map = await SalinityMap.find_all().sort("-generated_at").limit(1).to_list()
    if not latest_map:
        raise HTTPException(status_code=404, detail="No salinity map available.")
    return {"geojson_contours": latest_map[0].geojson_contours}

@router.get("/map/intrusion-front")
async def get_intrusion_front():
    """API-04: Return the intrusion_front GeoJSON from the latest SalinityMaps document."""
    latest_map = await SalinityMap.find_all().sort("-generated_at").limit(1).to_list()
    if not latest_map:
        raise HTTPException(status_code=404, detail="No salinity map available.")
    return {"intrusion_front": latest_map[0].intrusion_front}


# ==========================================
# ML Forecasts
# ==========================================

@router.get("/forecasts/{node_id}")
async def get_node_forecast(node_id: PydanticObjectId):
    """API-05: Return the latest 30/60/90-day EC forecast for a node."""
    forecasts = await Forecast.find(Forecast.node_id == node_id).sort("-generated_at").limit(3).to_list()
    if not forecasts:
        raise HTTPException(status_code=404, detail="No forecasts available for this node.")
    return {"forecasts": forecasts}


# ==========================================
# Alerts & Farmers
# ==========================================

@router.get("/alerts")
async def get_alerts(
    risk_class: Optional[str] = None,
    from_date: Optional[datetime] = None
):
    """API-06: List alert log with optional query filters."""
    query = Alert.find_all()
    if risk_class:
        query = query.find(Alert.risk_class == risk_class)
    if from_date:
        query = query.find(Alert.triggered_at >= from_date)
        
    alerts = await query.sort("-triggered_at").to_list()
    return {"alerts": alerts}

@router.post("/farmers/register", status_code=status.HTTP_201_CREATED)
async def register_farmer(farmer: Farmer):
    """API-07: Register a new farmer."""
    await farmer.insert()
    return {"message": "Farmer registered successfully", "farmer_id": str(farmer.id)}


# ==========================================
# Simulation (Demo Purposes)
# ==========================================

@router.post("/simulate/spike")
async def simulate_salinity_spike(node_id: PydanticObjectId):
    """
    API-08: Inject a sudden salinity spike event (+3.0 dS/m) into a specific node's 
    latest reading for demonstration and testing purposes.
    """
    # 1. Ensure node exists
    node = await SensorNode.get(node_id)
    if not node:
        raise HTTPException(status_code=404, detail="Node not found.")
        
    # 2. Get latest reading
    latest_reading = await SensorReading.find(
        SensorReading.node_id == node_id
    ).sort("-timestamp").limit(1).to_list()
    
    if not latest_reading:
        raise HTTPException(status_code=400, detail="No baseline reading to spike from.")
        
    baseline = latest_reading[0]
    
    # 3. Duplicate and spike
    spiked_reading = SensorReading(
        node_id=baseline.node_id,
        timestamp=datetime.now(), # Real-time spike
        ec_ds_m=baseline.ec_ds_m + 3.0, # The core injection logic
        ph=baseline.ph,
        moisture_pct=baseline.moisture_pct,
        is_simulated=True,
        raw_payload={"source": "api_spike_injection"}
    )
    
    await spiked_reading.insert()
    
    return {
        "message": "Salinity spike injected successfully.",
        "previous_ec": baseline.ec_ds_m,
        "new_ec": spiked_reading.ec_ds_m,
        "node_id": str(node_id)
    }
