import logging
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

from app.services.intelligence_service import generate_node_forecasts, generate_salinity_map
from app.services.alert_service import evaluate_alerts

logger = logging.getLogger(__name__)

def setup_scheduler() -> AsyncIOScheduler:
    """
    Initializes and configures the APScheduler.
    """
    scheduler = AsyncIOScheduler()
    
    # 1. Mock Data Ingestion (Placeholder - Normally fetches from physical sensors)
    # scheduler.add_job(mock_data_ingestion, IntervalTrigger(hours=6))
    
    # 2. Intelligence Services (Forecasting & Kriging)
    # We run this every 6 hours after data ingestion
    scheduler.add_job(
        generate_node_forecasts, 
        IntervalTrigger(hours=6), 
        id="node_forecasts", 
        replace_existing=True
    )
    
    scheduler.add_job(
        generate_salinity_map, 
        IntervalTrigger(hours=6), 
        id="salinity_map", 
        replace_existing=True
    )
    
    # 3. Alert Evaluation
    # Evaluates thresholds against the latest data every 30 minutes
    scheduler.add_job(
        evaluate_alerts, 
        IntervalTrigger(minutes=30), 
        id="evaluate_alerts", 
        replace_existing=True
    )
    
    return scheduler
