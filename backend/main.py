import jwt
from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from uuid import UUID
from datetime import datetime, timedelta
from typing import Optional

from config import settings
from database import get_db, engine
from models import Base, Facility, Staff, InventoryItem, FootfallLog
from dependencies import RequireRole, validate_facility_scope, validate_district_scope, get_current_user
from voice import router as voice_router

# Ensure tables are created (especially if running in local sqlite without alembic for quick tests)
Base.metadata.create_all(bind=engine)

app = FastAPI(title="Swasthya Grid API", version="1.0.0")

app.include_router(voice_router)

# Enable CORS for Next.js frontend calls
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/health-check")
def health_check():
    return {"status": "healthy", "timestamp": datetime.utcnow().isoformat()}

# Helper route to fetch seeded facilities (useful for populating login drop-downs)
@app.get("/api/v1/facilities")
def get_facilities(db: Session = Depends(get_db)):
    facilities = db.query(Facility).all()
    return [
        {
            "id": str(f.id),
            "name": f.name,
            "type": f.type,
            "district_code": f.district_code,
            "sanctioned_beds": f.sanctioned_beds,
            "available_beds": f.available_beds,
            "sanctioned_staff": f.sanctioned_staff,
        }
        for f in facilities
    ]

# Helper route for mock login to generate a JWT locally when settings.USE_MOCK_AUTH is True
@app.post("/api/v1/auth/mock-login")
def mock_login(payload: dict):
    if not settings.USE_MOCK_AUTH:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Mock login is disabled in production mode"
        )
    
    role = payload.get("role")
    email = payload.get("email", f"{role}@swasthyagrid.gov.in")
    facility_id = payload.get("facility_id")
    district_code = payload.get("district_code")
    
    if role not in ["receptionist", "phc_incharge", "district_admin"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid role requested"
        )
        
    # Generate JWT token
    claims = {
        "sub": email,
        "email": email,
        "role": role,
        "exp": datetime.utcnow() + timedelta(hours=24)
    }
    
    if role in ["receptionist", "phc_incharge"] and facility_id:
        claims["facility_id"] = str(facility_id)
    elif role == "district_admin" and district_code:
        claims["district_code"] = district_code
        
    token = jwt.encode(claims, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)
    return {"access_token": token, "token_type": "bearer", "claims": claims}


# PROTECTED ROUTES
# 1. Receptionist Data Endpoint (Facility-scoped)
@app.get(
    "/api/v1/receptionist/data/{facility_id}",
    dependencies=[Depends(RequireRole(["receptionist", "district_admin"])), Depends(validate_facility_scope)]
)
def get_receptionist_dashboard_data(facility_id: UUID, db: Session = Depends(get_db)):
    facility = db.query(Facility).filter(Facility.id == facility_id).first()
    if not facility:
        raise HTTPException(status_code=404, detail="Facility not found")
        
    staff_count = db.query(Staff).filter(Staff.facility_id == facility_id).count()
    inventory_items = db.query(InventoryItem).filter(InventoryItem.facility_id == facility_id).all()
    footfall_logs = db.query(FootfallLog).filter(FootfallLog.facility_id == facility_id).all()
    
    return {
        "facility_name": facility.name,
        "facility_type": facility.type,
        "available_beds": facility.available_beds,
        "sanctioned_beds": facility.sanctioned_beds,
        "staff_count": staff_count,
        "recent_footfall": [{"date": str(log.date), "count": log.count} for log in footfall_logs[:5]],
        "inventory": [
            {
                "medicine_name": item.medicine_name,
                "current_stock": item.current_stock
            }
            for item in inventory_items
        ]
    }


# 2. PHC In-charge Data Endpoint (Facility-scoped, requires PHC In-charge or District Admin)
@app.get(
    "/api/v1/phc-incharge/data/{facility_id}",
    dependencies=[Depends(RequireRole(["phc_incharge", "district_admin"])), Depends(validate_facility_scope)]
)
def get_phc_incharge_dashboard_data(facility_id: UUID, db: Session = Depends(get_db)):
    facility = db.query(Facility).filter(Facility.id == facility_id).first()
    if not facility:
        raise HTTPException(status_code=404, detail="Facility not found")
        
    staff_list = db.query(Staff).filter(Staff.facility_id == facility_id).all()
    inventory_items = db.query(InventoryItem).filter(InventoryItem.facility_id == facility_id).all()
    
    # Calculate simple FSI (Stress index): daily footfall / (catchment * beds_baseline)
    # Since census and catchment pop. are stage 5, we'll return a stub or calculated index
    fsi_index = round(float(facility.sanctioned_beds - facility.available_beds) / max(facility.sanctioned_beds, 1), 2)
    
    return {
        "facility_name": facility.name,
        "facility_type": facility.type,
        "available_beds": facility.available_beds,
        "sanctioned_beds": facility.sanctioned_beds,
        "fsi_score": fsi_index,
        "staff": [{"name": member.name, "role": member.role} for member in staff_list],
        "inventory": [
            {
                "medicine_name": item.medicine_name,
                "current_stock": item.current_stock,
                "avg_daily_burn_rate": item.avg_daily_burn_rate,
                "drp_value": item.drp_value
            }
            for item in inventory_items
        ]
    }


# 3. District Admin Data Endpoint (District-scoped)
@app.get(
    "/api/v1/district-admin/data/{district_code}",
    dependencies=[Depends(RequireRole(["district_admin"])), Depends(validate_district_scope)]
)
def get_district_admin_dashboard_data(district_code: str, db: Session = Depends(get_db)):
    facilities = db.query(Facility).filter(Facility.district_code == district_code).all()
    
    results = []
    for f in facilities:
        staff_count = db.query(Staff).filter(Staff.facility_id == f.id).count()
        results.append({
            "facility_id": str(f.id),
            "facility_name": f.name,
            "facility_type": f.type,
            "available_beds": f.available_beds,
            "sanctioned_beds": f.sanctioned_beds,
            "staff_count": staff_count
        })
        
    return {
        "district_code": district_code,
        "total_facilities": len(facilities),
        "facilities": results
    }
