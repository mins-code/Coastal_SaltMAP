import asyncio
import os
import sys
import random
import numpy as np
import pandas as pd
from datetime import datetime, timezone, timedelta

# Ensure the 'app' module can be imported when running from the root
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.db.database import init_db
from app.models.models import SensorNode, EnvReading, SensorReading, GeoJSONPoint

async def generate_nodes(num_nodes=50):
    nodes = []
    soil_types = ['Sandy', 'Loamy', 'Clay']
    
    for i in range(num_nodes):
        lat = random.uniform(12.1, 12.6)
        lon = random.uniform(74.9, 75.2)
        elevation = random.uniform(1.0, 15.0)
        dist_coast = random.uniform(0.1, 5.0)
        soil = random.choice(soil_types)
        
        node = SensorNode(
            name=f"Kasaragod-Node-{i+1:03d}",
            location=GeoJSONPoint(coordinates=[lon, lat]),
            elevation_m=round(elevation, 2),
            distance_coast_km=round(dist_coast, 2),
            soil_type=soil,
            is_active=True
        )
        nodes.append(node)
        
    await SensorNode.insert_many(nodes)
    return nodes

def generate_env_dataframe(start_date, end_date):
    # Hourly frequency
    times = pd.date_range(start=start_date, end=end_date, freq='h', tz='UTC')
    df = pd.DataFrame({'timestamp': times})
    
    # 1. Tidal Height (12.4h cycle, -0.5m to 1.5m)
    # Amplitude = 1.0, Offset = 0.5 => ranges from -0.5 to 1.5
    hours_from_start = (df['timestamp'] - df['timestamp'].min()).dt.total_seconds() / 3600.0
    tide_base = 1.0 * np.sin(2 * np.pi * hours_from_start / 12.4) + 0.5
    
    # 2. Sea Level Anomaly (Monsoon: June(6) to Sept(9))
    months = df['timestamp'].dt.month
    is_monsoon = months.isin([6, 7, 8, 9])
    sla = np.where(is_monsoon, 0.2, 0.0)
    
    df['sea_level_anomaly_m'] = sla
    df['tidal_height_m'] = tide_base + sla
    
    # 3. Rainfall (Highly seasonal)
    # 10 to 100mm/day during monsoon, negligible otherwise
    # Distribute daily rain randomly across hours
    rain_hourly = np.where(
        is_monsoon,
        np.random.exponential(scale=1.5, size=len(df)), # Frequent small showers, occasional heavy
        np.random.exponential(scale=0.1, size=len(df))  # Dry season
    )
    # Cap and tune to roughly match 10-100mm/day in monsoon
    rain_hourly = np.clip(rain_hourly, 0, 15) 
    df['rainfall_mm'] = np.round(rain_hourly, 2)
    
    return df

async def generate_env_readings(df_env, batch_size=5000):
    records = []
    # Arbitrary reference location for general env readings
    ref_loc = GeoJSONPoint(coordinates=[75.0, 12.35])
    
    for row in df_env.itertuples():
        records.append(EnvReading(
            timestamp=row.timestamp,
            rainfall_mm=row.rainfall_mm,
            tidal_height_m=row.tidal_height_m,
            sea_level_anomaly_m=row.sea_level_anomaly_m,
            source="Simulated_Regional_Model",
            location=ref_loc
        ))
        
        if len(records) >= batch_size:
            await EnvReading.insert_many(records)
            records = []
            
    if records:
        await EnvReading.insert_many(records)

async def generate_sensor_readings(nodes, df_env, batch_size=5000):
    # Pre-calculate rolling aggregates
    df_env['tide_rolling_12h_max'] = df_env['tidal_height_m'].rolling(window=12, min_periods=1).max()
    df_env['rain_rolling_48h_sum'] = df_env['rainfall_mm'].rolling(window=48, min_periods=1).sum()
    
    total_months = 24
    start_time = df_env['timestamp'].min()
    
    for month in range(total_months):
        print(f"  -> Generating and inserting SensorReadings for Month {month+1}/{total_months}...")
        
        month_start = start_time + pd.DateOffset(months=month)
        month_end = start_time + pd.DateOffset(months=month+1)
        
        # Filter env data for this month
        mask = (df_env['timestamp'] >= month_start) & (df_env['timestamp'] < month_end)
        df_month = df_env[mask]
        
        if df_month.empty:
            continue
            
        records = []
        for node in nodes:
            # Soil multiplier
            soil_rates = {'Sandy': 1.5, 'Loamy': 1.0, 'Clay': 0.5}
            rate = soil_rates.get(node.soil_type, 1.0)
            
            # Baseline EC
            base_ec = max(0.5, 10.0 / node.distance_coast_km)
            
            # Physics calculations vectorized over the month
            # High tide intrusion effect
            intrusion = np.where(df_month['tide_rolling_12h_max'] > 1.2, 
                                 (df_month['tide_rolling_12h_max'] - 1.2) * 2.0 * rate / node.elevation_m, 
                                 0)
            
            # Rain freshening effect
            freshening = (df_month['rain_rolling_48h_sum'] / 100.0) * 1.5 * rate
            
            # Combine
            simulated_ec = base_ec + intrusion - freshening
            # Add noise
            noise = np.random.normal(0, 0.2, size=len(simulated_ec))
            simulated_ec = np.clip(simulated_ec + noise, 0.1, base_ec * 3) 
            simulated_ec = np.array(simulated_ec) # Convert to numpy array to reset index
            
            # Simulate correlation to Ph and moisture
            simulated_ph = np.clip(7.0 - (simulated_ec - base_ec) * 0.1, 5.5, 8.5)
            simulated_moisture = np.clip(20.0 + (np.array(df_month['rain_rolling_48h_sum']) * 0.5) - (simulated_ec * 0.5), 10.0, 90.0)
            
            # Create objects
            for i, row in enumerate(df_month.itertuples()):
                records.append(SensorReading(
                    node_id=node.id,
                    timestamp=row.timestamp,
                    ec_ds_m=round(simulated_ec[i], 3),
                    ph=round(simulated_ph[i], 2),
                    moisture_pct=round(simulated_moisture[i], 1),
                    is_simulated=True,
                    raw_payload={"source": "bulk_simulation"}
                ))
                
                if len(records) >= batch_size:
                    await SensorReading.insert_many(records)
                    records = []
                    
        # Insert any remaining for the month
        if records:
            await SensorReading.insert_many(records)

async def main():
    print("1. Connecting to MongoDB...")
    await init_db()
    
    print("2. Clearing existing historical data (Optional, skipping for safety)...")
    # await SensorNode.delete_all()
    # await EnvReading.delete_all()
    # await SensorReading.delete_all()
    
    print("3. Generating 50 Sensor Nodes...")
    nodes = await generate_nodes(50)
    print(f"   -> Inserted {len(nodes)} nodes.")
    
    print("4. Calculating Environmental timeseries (2 years)...")
    end_date = datetime.now(timezone.utc)
    start_date = end_date - timedelta(days=365*2)
    df_env = generate_env_dataframe(start_date, end_date)
    print(f"   -> Generated {len(df_env)} hourly timeframes.")
    
    print("5. Inserting EnvReadings in batches...")
    await generate_env_readings(df_env)
    print("   -> Completed EnvReadings.")
    
    print("6. Simulating and inserting SensorReadings...")
    await generate_sensor_readings(nodes, df_env)
    print("   -> Completed SensorReadings.")
    
    print("All Historical Data generated and inserted successfully!")

if __name__ == "__main__":
    asyncio.run(main())
