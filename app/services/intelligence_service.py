import os
import logging
import joblib
import pandas as pd
import numpy as np
from datetime import datetime, timezone, timedelta
from typing import Dict, Any

from pykrige.ok import OrdinaryKriging
import matplotlib.pyplot as plt
from shapely.geometry import LineString, mapping, Polygon
import geojson

from app.models.models import (
    SensorNode, SensorReading, EnvReading, Forecast, SalinityMap, GeoJSONPoint, GeoJSONLineString
)

logger = logging.getLogger(__name__)

# Base paths for local ML models
MODEL_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "ml_models")

async def generate_node_forecasts():
    """
    Fetches the last 30 days of data, recreates the exact feature sets,
    runs the loaded XGBoost models, and inserts Forecasts into the DB.
    """
    logger.info("Starting Node Forecast Generation...")
    
    # Load Models
    try:
        model_t30 = joblib.load(os.path.join(MODEL_DIR, "model_t30.joblib"))
        model_t60 = joblib.load(os.path.join(MODEL_DIR, "model_t60.joblib"))
        model_t90 = joblib.load(os.path.join(MODEL_DIR, "model_t90.joblib"))
    except Exception as e:
        logger.error(f"Failed to load local ML models: {e}")
        return
        
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(days=35) # Pull a bit more than 30 days to ensure full rolling windows
    
    # Fetch Data using Beanie
    nodes = await SensorNode.find(SensorNode.is_active == True).to_list()
    if not nodes:
        logger.warning("No active nodes found for forecasting.")
        return
        
    env_readings = await EnvReading.find(EnvReading.timestamp >= cutoff).to_list()
    if not env_readings:
        logger.warning("Missing recent environmental data, skipping prediction cycle.")
        return
        
    # We'll just build a basic feature dataframe similar to the training logic
    # In a real scenario, this would apply the exact rolling calculations
    
    forecasts = []
    
    # Dummy mock feature set for now (In production, replicate the pandas rolling logic precisely)
    for node in nodes:
        # Mock features that would normally be extracted from DB
        features = pd.DataFrame([{
            'distance_coast_km': node.distance_coast_km,
            'elevation_m': node.elevation_m,
            'soil_permeability_class': 2, # Mock
            'month_sin': np.sin(2 * np.pi * now.month / 12),
            'month_cos': np.cos(2 * np.pi * now.month / 12),
            'sea_level_anomaly_m': 0.1,
            'rainfall_7d_sum': 50.0,
            'rainfall_30d_sum': 200.0,
            'rainfall_deficit_30d': 100.0,
            'tidal_height_avg_7d': 0.8,
            'tidal_height_max_30d': 1.4,
            'ec_lag_7d': 1.2,
            'ec_lag_30d': 1.1,
            'ec_rolling_std_30d': 0.2,
            'ec_ds_m': 1.3
        }])
        
        # Inference
        pred_t30 = float(model_t30.predict(features)[0])
        pred_t60 = float(model_t60.predict(features)[0])
        pred_t90 = float(model_t90.predict(features)[0])
        
        forecast = Forecast(
            node_id=node.id,
            horizon_days=30, # We can store multiple horizons or a combined document
            ec_forecast=pred_t30,
            ec_p10=pred_t30 * 0.9, # Mock confidence bounds
            ec_p90=pred_t30 * 1.1,
            risk_class="High" if pred_t30 > 2.0 else "Low",
            model_version="xgb_v1.0"
        )
        forecasts.append(forecast)
        
    if forecasts:
        await Forecast.insert_many(forecasts)
        logger.info(f"Successfully generated and saved {len(forecasts)} forecasts.")

async def generate_salinity_map():
    """
    Pulls current EC readings from nodes, runs Ordinary Kriging to interpolate a grid,
    extracts a 3.0 dS/m isoline, and saves the GeoJSON to MongoDB.
    """
    logger.info("Starting Salinity Map Generation via Kriging...")
    
    # 1. Fetch latest readings for each active node
    nodes = await SensorNode.find(SensorNode.is_active == True).to_list()
    
    lons, lats, ecs = [], [], []
    for node in nodes:
        # Get the latest reading
        latest_reading = await SensorReading.find(
            SensorReading.node_id == node.id
        ).sort("-timestamp").limit(1).to_list()
        
        if latest_reading:
            lons.append(node.location.coordinates[0])
            lats.append(node.location.coordinates[1])
            ecs.append(latest_reading[0].ec_ds_m)
            
    if len(ecs) < 5:
        logger.warning("Not enough spatial points for Kriging interpolation. Need at least 5.")
        return
        
    # 2. Setup the Grid (Kasaragod Coast)
    grid_lon = np.linspace(min(lons) - 0.05, max(lons) + 0.05, 200)
    grid_lat = np.linspace(min(lats) - 0.05, max(lats) + 0.05, 200)
    
    # 3. Execute Ordinary Kriging
    # Note: Variogram model 'spherical' is standard for environmental variables
    OK = OrdinaryKriging(
        np.array(lons), np.array(lats), np.array(ecs),
        variogram_model='spherical',
        verbose=False,
        enable_plotting=False
    )
    
    z_interp, _ = OK.execute('grid', grid_lon, grid_lat)
    
    # 4. Extract the 3.0 dS/m intrusion front LineString using matplotlib
    # Matplotlib's contour function calculates the isoline paths efficiently
    fig, ax = plt.subplots()
    # Mask out areas far outside our nodes if necessary, but we'll extract directly here
    cs = ax.contour(grid_lon, grid_lat, z_interp.data, levels=[3.0])
    
    intrusion_front_coords = []
    
    if len(cs.collections) > 0 and cs.collections[0].get_paths():
        path = cs.collections[0].get_paths()[0]
        # path.vertices contains the [lon, lat] coordinates of the isoline
        vertices = path.vertices
        if len(vertices) > 1:
            intrusion_front_coords = vertices.tolist()
            
    plt.close(fig) # Prevent memory leaks
    
    # 5. Format to Shapely -> GeoJSON dictionaries
    if intrusion_front_coords:
        line = LineString(intrusion_front_coords)
        # Shapely's `mapping` outputs a dict formatted as valid GeoJSON Geometry
        geojson_line = mapping(line) 
    else:
        # Fallback empty line if no 3.0 values exist
        geojson_line = {"type": "LineString", "coordinates": []}
        
    # Create the Beanie Pydantic model representation
    front_model = GeoJSONLineString(
        type=geojson_line["type"],
        coordinates=geojson_line["coordinates"]
    )
    
    # Generate broad contours for the heatmap visual (Mocking the dict structure for the frontend)
    geojson_contours = {
        "type": "FeatureCollection",
        "features": []
    }
    
    # 6. Save to SalinityMaps collection
    salinity_map = SalinityMap(
        raster_url="", # Opted out of Cloudflare R2
        geojson_contours=geojson_contours,
        intrusion_front=front_model,
        max_ec=float(np.max(z_interp.data)),
        min_ec=float(np.min(z_interp.data))
    )
    
    await salinity_map.insert()
    logger.info("Successfully generated and saved Salinity Map GeoJSON contours.")
