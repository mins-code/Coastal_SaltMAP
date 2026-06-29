import logging
from datetime import datetime, timezone, timedelta
from typing import Optional

from app.models.models import Farmer, SensorReading, Forecast, Alert, SensorNode

logger = logging.getLogger(__name__)

async def send_sms_alert(phone: str, message: str):
    """
    Stub function for Twilio SMS integration.
    Currently outputs to the console.
    """
    logger.info(f"--- SMS ALERT DISPATCHED ---")
    logger.info(f"To: {phone}")
    logger.info(f"Message: {message}")
    logger.info(f"----------------------------")

async def evaluate_alerts():
    """
    Checks the latest EC readings and T+30 forecasts against registered farmers' crops.
    Applies advisory logic and deduplicates alerts within a 48-hour window.
    """
    logger.info("Evaluating alerts for farmers...")
    now = datetime.now(timezone.utc)
    cooldown_period = now - timedelta(hours=48)
    
    # Get all active farmers
    farmers = await Farmer.find(Farmer.is_active == True).to_list()
    if not farmers:
        return
        
    for farmer in farmers:
        node_id = farmer.node_id.id
        
        # 1. Deduplication Check
        # Check if an alert was already triggered for this farmer and node within 48 hours
        recent_alert = await Alert.find(
            Alert.farmer_id == farmer.id,
            Alert.node_id == node_id,
            Alert.triggered_at >= cooldown_period
        ).limit(1).to_list()
        
        if recent_alert:
            # Skip this farmer to avoid spamming
            continue
            
        # 2. Fetch latest readings and forecasts
        latest_reading = await SensorReading.find(
            SensorReading.node_id == node_id
        ).sort("-timestamp").limit(1).to_list()
        
        latest_forecast = await Forecast.find(
            Forecast.node_id == node_id,
            Forecast.horizon_days == 30
        ).sort("-generated_at").limit(1).to_list()
        
        current_ec = latest_reading[0].ec_ds_m if latest_reading else 0.0
        forecast_ec = latest_forecast[0].ec_forecast if latest_forecast else 0.0
        
        # Determine the maximum risk value between current and forecasted
        evaluated_ec = max(current_ec, forecast_ec)
        
        # 3. Advisory Logic Implementation
        if evaluated_ec < 1.0:
            risk_class = "Safe (Green)"
            advisory = "No action needed. Groundwater quality is good."
        elif 1.0 <= evaluated_ec < 2.0:
            risk_class = "Watch (Yellow)"
            advisory = "Monitor weekly. Avoid expanding paddy area this season."
        elif 2.0 <= evaluated_ec < 3.0:
            risk_class = "Caution (Orange)"
            advisory = "Consider salt-tolerant paddy variety (CST 7-1, Vytilla-1)."
        elif 3.0 <= evaluated_ec <= 5.0:
            risk_class = "Risk (Red)"
            advisory = "Paddy not recommended. Switch to coconut or salt-tolerant banana."
        else:
            risk_class = "Critical (Dark Red)"
            advisory = "Do not irrigate with groundwater. Seek alternative water source."
            
        # 4. Trigger threshold (Example: Only trigger if > 2.0 for paddy, or globally just trigger if not Safe)
        # Assuming we trigger if it hits Caution, Risk, or Critical
        if evaluated_ec >= 2.0:
            alert_doc = Alert(
                farmer_id=farmer.id,
                node_id=node_id,
                triggered_at=now,
                ec_value=evaluated_ec,
                risk_class=risk_class,
                advisory_text_en=advisory,
                advisory_text_kn=advisory, # Placeholder for translation
                channel="sms",
                status="sent"
            )
            await alert_doc.insert()
            
            # Dispatch the SMS
            sms_body = f"SaltMAP Alert [{risk_class}]: EC is {evaluated_ec:.2f} dS/m. {advisory}"
            await send_sms_alert(farmer.phone, sms_body)
            
    logger.info("Alert evaluation complete.")
