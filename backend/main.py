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
from webhook import router as webhook_router
from reference_service import get_census_data


# Ensure tables are created (especially if running in local sqlite without alembic for quick tests)
Base.metadata.create_all(bind=engine)

app = FastAPI(title="Swasthya Grid API", version="1.0.0")

app.include_router(voice_router)
app.include_router(webhook_router)

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
def calculate_fsi_for_facility(facility: Facility, db: Session) -> float:
    census_data = get_census_data(facility.district_code, db)
    catchment_pop = census_data["catchment_population"] if (census_data and census_data["catchment_population"] > 0) else 1
    beds_baseline = facility.sanctioned_beds if facility.sanctioned_beds > 0 else 1
    
    footfall = db.query(FootfallLog).filter(FootfallLog.facility_id == facility.id).order_by(FootfallLog.date.desc()).first()
    footfall_count = footfall.count if footfall else 0
    
    return round(float(footfall_count) / (catchment_pop * beds_baseline), 6)

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
    
    fsi_index = calculate_fsi_for_facility(facility, db)
    
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


# FSI Endpoints
@app.get(
    "/api/v1/fsi/{facility_id}",
    dependencies=[Depends(RequireRole(["receptionist", "phc_incharge", "district_admin"])), Depends(validate_facility_scope)]
)
def get_facility_fsi(facility_id: UUID, db: Session = Depends(get_db)):
    facility = db.query(Facility).filter(Facility.id == facility_id).first()
    if not facility:
        raise HTTPException(status_code=404, detail="Facility not found")
        
    census_data = get_census_data(facility.district_code, db)
    catchment_pop = census_data["catchment_population"] if (census_data and census_data["catchment_population"] > 0) else 1
    beds_baseline = facility.sanctioned_beds if facility.sanctioned_beds > 0 else 1
    
    footfall = db.query(FootfallLog).filter(FootfallLog.facility_id == facility.id).order_by(FootfallLog.date.desc()).first()
    footfall_count = footfall.count if footfall else 0
    
    fsi_value = calculate_fsi_for_facility(facility, db)
    
    return {
        "facility_id": str(facility.id),
        "facility_name": facility.name,
        "district_code": facility.district_code,
        "real_time_daily_footfall": footfall_count,
        "census_catchment_population": catchment_pop,
        "available_beds_baseline": beds_baseline,
        "fsi_value": fsi_value
    }


@app.get(
    "/api/v1/fsi/district/{district_code}",
    dependencies=[Depends(RequireRole(["district_admin"])), Depends(validate_district_scope)]
)
def get_district_fsi(district_code: str, db: Session = Depends(get_db)):
    facilities = db.query(Facility).filter(Facility.district_code == district_code).all()
    if not facilities:
        raise HTTPException(status_code=404, detail="No facilities found for this district")
        
    facility_fsi_list = []
    total_fsi = 0.0
    for f in facilities:
        fsi_val = calculate_fsi_for_facility(f, db)
        total_fsi += fsi_val
        facility_fsi_list.append({
            "facility_id": str(f.id),
            "facility_name": f.name,
            "fsi_value": fsi_val
        })
        
    avg_fsi = round(total_fsi / len(facilities), 6) if facilities else 0.0
    
    return {
        "district_code": district_code,
        "average_fsi": avg_fsi,
        "facilities": facility_fsi_list
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
