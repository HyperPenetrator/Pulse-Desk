import os
import sys
from sqlalchemy.orm import Session

# Set path to import models and config
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))
from models import InventoryItem, Facility, Alert
from reference_service import get_nfhs_data

def recompute_drp_and_alerts(db: Session) -> dict:
    items = db.query(InventoryItem).all()
    updated_count = 0
    alert_count = 0
    
    for item in items:
        facility = db.query(Facility).filter(Facility.id == item.facility_id).first()
        if not facility:
            continue
            
        # Get NFHS seasonal vector weight
        nfhs_data = get_nfhs_data(facility.district_code, db)
        vector_weight = nfhs_data["seasonal_vector_weight"] if (nfhs_data and "seasonal_vector_weight" in nfhs_data) else 0.0
        
        # Calculate DRP = (Average Daily Burn Rate * Supply Lead Time) + NFHS Seasonal Vector Weight
        drp_value = (item.avg_daily_burn_rate * item.supply_lead_time) + vector_weight
        item.drp_value = round(drp_value, 4)
        updated_count += 1
        
        # Check if current stock falls below recomputed DRP
        if item.current_stock < item.drp_value:
            # Check if there is an active stock-out alert for this facility
            # (Optionally, we can check if it already exists to avoid duplicate rows)
            existing_alert = db.query(Alert).filter(
                Alert.facility_id == item.facility_id,
                Alert.type == "stock-out",
                Alert.status == "active"
            ).first()
            
            if not existing_alert:
                new_alert = Alert(
                    type="stock-out",
                    facility_id=item.facility_id,
                    status="active"
                )
                db.add(new_alert)
                alert_count += 1
                
    db.commit()
    return {
        "updated_items": updated_count,
        "new_alerts_triggered": alert_count
    }
