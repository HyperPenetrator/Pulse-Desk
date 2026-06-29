import jwt
import math
import requests
import os
from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from uuid import UUID
from datetime import datetime, timedelta
from typing import Optional
from pydantic import BaseModel

from config import settings
from database import get_db, engine
from models import Base, Facility, Staff, InventoryItem, FootfallLog, PatientSession, Dispatch, Alert
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


class IntakePayload(BaseModel):
    symptom: str
    lat: float
    lng: float
    location_name: Optional[str] = None


# Triage severity classification (keyword lookup, structured as swappable function)
# Note: This can later call the Dialogflow CX intent classifier from Stage 4.
def classify_severity(symptom: str) -> str:
    emergency_keywords = [
        "chest pain", "breathing", "unconscious", "heart attack", "stroke",
        "bleeding", "accident", "emergency", "fracture", "severe", "drowning",
        "choking", "poison", "burn", "suicide", "seizure", "paralysis",
        "breathing difficulty", "head injury", "breathlessness", "heart pain"
    ]
    symptom_lower = symptom.lower()
    for keyword in emergency_keywords:
        if keyword in symptom_lower:
            return "emergency"
    return "non-emergency"


def get_distance_matrix(origin_lat: float, origin_lng: float, destinations: list[tuple[float, float, str]], api_key: Optional[str] = None) -> list[dict]:
    """
    Computes distance matrix. If api_key is available, calls Google Maps Distance Matrix API.
    Otherwise, simulates responses based on straight-line distance and a speed of 40 km/h.
    destinations is a list of tuples: (lat, lng, facility_name)
    """
    results = []
    if api_key:
        dest_strings = "|".join([f"{d[0]},{d[1]}" for d in destinations])
        url = f"https://maps.googleapis.com/maps/api/distancematrix/json?origins={origin_lat},{origin_lng}&destinations={dest_strings}&key={api_key}"
        try:
            resp = requests.get(url, timeout=5)
            if resp.status_code == 200:
                data = resp.json()
                if data.get("status") == "OK" and "rows" in data and len(data["rows"]) > 0:
                    elements = data["rows"][0]["elements"]
                    for idx, elem in enumerate(elements):
                        if elem.get("status") == "OK":
                            dist_meters = elem["distance"]["value"]
                            duration_seconds = elem["duration"]["value"]
                            results.append({
                                "facility_name": destinations[idx][2],
                                "distance_meters": dist_meters,
                                "duration_seconds": duration_seconds,
                                "eta_minutes": math.ceil(duration_seconds / 60)
                            })
                            continue
        except Exception:
            pass
            
    # Mock / simulation fallback
    if not results:
        # Earth radius in km
        R = 6371.0
        for lat, lng, name in destinations:
            # Calculate distance using haversine formula
            dlat = math.radians(lat - origin_lat)
            dlng = math.radians(lng - origin_lng)
            a = math.sin(dlat / 2)**2 + math.cos(math.radians(origin_lat)) * math.cos(math.radians(lat)) * math.sin(dlng / 2)**2
            c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
            distance_km = R * c
            
            # Assume 40 km/h average speed in traffic
            speed_km_min = 40.0 / 60.0
            eta_mins = max(1, math.ceil(distance_km / speed_km_min))
            results.append({
                "facility_name": name,
                "distance_meters": int(distance_km * 1000),
                "duration_seconds": int(eta_mins * 60),
                "eta_minutes": eta_mins
            })
            
    return results


def mirror_alert_to_firestore(alert_id: str, alert_type: str, status: str, facility_id: Optional[str] = None, district_code: Optional[str] = None):
    try:
        if settings.FIREBASE_PROJECT_ID:
            from google.cloud import firestore
            fs_client = firestore.Client(project=settings.FIREBASE_PROJECT_ID)
            doc_ref = fs_client.collection("alerts").document(alert_id)
            doc_ref.set({
                "id": alert_id,
                "type": alert_type,
                "facility_id": facility_id,
                "district_code": district_code,
                "status": status,
                "created_at": datetime.utcnow().isoformat()
            })
            print(f"Mirrored alert {alert_id} to Firestore.")
        else:
            print(f"[Simulated Firestore] Alert {alert_id} mirrored: {alert_type}, facility_id={facility_id}, district_code={district_code}")
    except Exception as e:
        print(f"Error mirroring alert to Firestore: {e}")


def mirror_dispatch_to_firestore(dispatch_id: str, patient_session_id: str, facility_id: str, status: str, lat: float, lng: float, eta_mins: int):
    try:
        if settings.FIREBASE_PROJECT_ID:
            from google.cloud import firestore
            fs_client = firestore.Client(project=settings.FIREBASE_PROJECT_ID)
            doc_ref = fs_client.collection("dispatches").document(dispatch_id)
            doc_ref.set({
                "id": dispatch_id,
                "patient_session_id": patient_session_id,
                "facility_id": facility_id,
                "status": status,
                "lat": lat,
                "lng": lng,
                "eta_minutes": eta_mins,
                "created_at": datetime.utcnow().isoformat()
            })
            print(f"Mirrored dispatch {dispatch_id} to Firestore.")
        else:
            print(f"[Simulated Firestore] Dispatch {dispatch_id} mirrored: facility_id={facility_id}, eta_mins={eta_mins}")
    except Exception as e:
        print(f"Error mirroring dispatch to Firestore: {e}")


@app.post("/api/v1/intake")
def post_intake(payload: IntakePayload, db: Session = Depends(get_db)):
    severity = classify_severity(payload.symptom)
    
    # Save Patient Session
    patient_session = PatientSession(
        channel="web",
        raw_text=payload.symptom,
        language_code="en",
        confidence_score=1.0,
        severity=severity,
        created_at=datetime.utcnow()
    )
    db.add(patient_session)
    db.flush()  # Populates patient_session.id
    
    if severity == "emergency":
        # Check facilities with available beds > 0
        capable_facilities = db.query(Facility).filter(Facility.available_beds > 0).all()
        
        # Configurable radius in meters (50 km)
        CONFIGURABLE_RADIUS_METERS = 50000.0
        
        # We also query all facilities to find nearest overall for escalation scope if needed
        all_facilities = db.query(Facility).all()
        
        selected_facility = None
        eta_minutes = None
        
        if capable_facilities:
            destinations = [(f.lat or 0.0, f.lng or 0.0, f.name) for f in capable_facilities]
            # Use GOOGLE_MAPS_API_KEY from environment if available
            maps_key = os.environ.get("GOOGLE_MAPS_API_KEY")
            distances = get_distance_matrix(payload.lat, payload.lng, destinations, api_key=maps_key)
            
            # Match back to facility and filter by radius
            within_radius_facilities = []
            for idx, dist_info in enumerate(distances):
                facility = capable_facilities[idx]
                if dist_info["distance_meters"] <= CONFIGURABLE_RADIUS_METERS:
                    within_radius_facilities.append((facility, dist_info))
            
            if within_radius_facilities:
                # Sort by distance
                within_radius_facilities.sort(key=lambda x: x[1]["distance_meters"])
                selected_facility, dist_info = within_radius_facilities[0]
                eta_minutes = dist_info["eta_minutes"]
                
        if selected_facility:
            # Create Dispatch
            eta_time = datetime.utcnow() + timedelta(minutes=eta_minutes)
            dispatch = Dispatch(
                patient_session_id=patient_session.id,
                facility_id=selected_facility.id,
                status="pending",
                lat=payload.lat,
                lng=payload.lng,
                eta=eta_time
            )
            db.add(dispatch)
            
            # Create Alert of type surge
            alert = Alert(
                type="surge",
                facility_id=selected_facility.id,
                status="active",
                created_at=datetime.utcnow()
            )
            db.add(alert)
            db.commit()
            
            # Mirror to Firestore
            mirror_dispatch_to_firestore(str(dispatch.id), str(patient_session.id), str(selected_facility.id), "pending", payload.lat, payload.lng, eta_minutes)
            mirror_alert_to_firestore(str(alert.id), "surge", "active", facility_id=str(selected_facility.id))
            
            return {
                "status": "dispatched",
                "severity": severity,
                "facility_name": selected_facility.name,
                "eta": eta_minutes
            }
        else:
            # No facility with capacity within radius -> Escalate to district-admin scope
            # Find closest facility overall to determine the district code
            closest_district = "UNKNOWN"
            if all_facilities:
                destinations = [(f.lat or 0.0, f.lng or 0.0, f.name) for f in all_facilities]
                maps_key = os.environ.get("GOOGLE_MAPS_API_KEY")
                all_distances = get_distance_matrix(payload.lat, payload.lng, destinations, api_key=maps_key)
                
                # Sort overall facilities by distance
                sorted_overall = sorted(enumerate(all_distances), key=lambda x: x[1]["distance_meters"])
                closest_index = sorted_overall[0][0]
                closest_district = all_facilities[closest_index].district_code
            
            # Create Alert escalated directly to district-admin scope (facility_id = None, district_code set)
            alert = Alert(
                type="surge",
                facility_id=None,
                district_code=closest_district,
                status="active",
                created_at=datetime.utcnow()
            )
            db.add(alert)
            db.commit()
            
            # Mirror to Firestore
            mirror_alert_to_firestore(str(alert.id), "surge", "active", facility_id=None, district_code=closest_district)
            
            return {
                "status": "escalated",
                "severity": severity,
                "message": "No nearby facility with capacity. Escalated to district-admin.",
                "district_code": closest_district
            }
            
    else:
        # non-emergency
        db.commit()
        return {
            "status": "triage",
            "severity": severity,
            "message": "Non-emergency detected. Please consult your nearest Primary Health Centre (PHC)."
        }


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
