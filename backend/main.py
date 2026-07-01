import jwt
import math
import requests
import os
import redis
from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from uuid import UUID
from datetime import datetime, timedelta
from typing import Optional
from pydantic import BaseModel

from config import settings
from database import get_db, engine
from models import Base, Facility, Staff, InventoryItem, FootfallLog, PatientSession, Dispatch, Alert, AttendanceLog
from dependencies import RequireRole, validate_facility_scope, validate_district_scope, get_current_user
from voice import router as voice_router
from webhook import router as webhook_router
from reference_service import get_census_data


# Ensure tables are created (especially if running in local sqlite without alembic for quick tests)
Base.metadata.create_all(bind=engine)

redis_client = redis.Redis(host=os.getenv('REDIS_HOST', 'localhost'), port=6379, decode_responses=True)

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
    dependencies=[Depends(RequireRole(["receptionist", "district_admin", "phc_incharge"])), Depends(validate_facility_scope)]
)
def get_receptionist_dashboard_data(facility_id: UUID, db: Session = Depends(get_db)):
    facility = db.query(Facility).filter(Facility.id == facility_id).first()
    if not facility:
        raise HTTPException(status_code=404, detail="Facility not found")
        
    staff_count = db.query(Staff).filter(Staff.facility_id == facility_id).count()
    inventory_items = db.query(InventoryItem).filter(InventoryItem.facility_id == facility_id).all()
    footfall_logs = db.query(FootfallLog).filter(FootfallLog.facility_id == facility_id).all()
    
    # Query dispatches for this facility
    dispatches = db.query(Dispatch).filter(Dispatch.facility_id == facility_id).all()
    
    active_dispatches = [
        {
            "id": str(d.id),
            "patient_session_id": str(d.patient_session_id),
            "status": d.status,
            "lat": d.lat,
            "lng": d.lng,
            "eta": d.eta.isoformat() if d.eta else None,
            "symptom": d.patient_session.raw_text if d.patient_session else ""
        }
        for d in dispatches if d.status in ["pending", "enroute"]
    ]
    
    walk_ins = [
        {
            "id": str(d.patient_session.id),
            "symptoms": d.patient_session.raw_text,
            "severity": d.patient_session.severity,
            "created_at": d.patient_session.created_at.isoformat()
        }
        for d in dispatches if d.patient_session and d.patient_session.channel == "walk-in"
    ]
    
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
        ],
        "active_dispatches": active_dispatches,
        "walk_ins": walk_ins
    }



# 2. PHC In-charge Data Endpoint (Facility-scoped, requires PHC In-charge or District Admin)
def calculate_fsi_for_facility(facility: Facility, db: Session) -> int:
    cache_key = f"fsi:facility:{facility.id}"
    try:
        cached = redis_client.get(cache_key)
        if cached is not None:
            return int(cached)
    except Exception as e:
        print(f"Redis cache read error: {e}")

    census_data = get_census_data(facility.district_code, db)
    catchment_pop = census_data["catchment_population"] if (census_data and census_data["catchment_population"] > 0) else 1
    beds_baseline = facility.sanctioned_beds if facility.sanctioned_beds > 0 else 1
    
    footfall = db.query(FootfallLog).filter(FootfallLog.facility_id == facility.id).order_by(FootfallLog.date.desc()).first()
    footfall_count = footfall.count if footfall else 0
    
    raw_fsi = float(footfall_count) / (catchment_pop * beds_baseline)
    fsi_int = int(raw_fsi * 1000000)
    
    try:
        redis_client.setex(cache_key, 60, str(fsi_int))
    except Exception as e:
        print(f"Redis cache write error: {e}")
        
    return fsi_int

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
        
    avg_fsi = int(total_fsi / len(facilities)) if facilities else 0
    
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


class DispatchStatusUpdatePayload(BaseModel):
    status: str

@app.patch(
    "/api/v1/dispatch/{id}",
    dependencies=[Depends(RequireRole(["receptionist", "district_admin", "phc_incharge"]))]
)
def patch_dispatch(id: UUID, payload: DispatchStatusUpdatePayload, db: Session = Depends(get_db), claims: dict = Depends(get_current_user)):
    dispatch = db.query(Dispatch).filter(Dispatch.id == id).first()
    if not dispatch:
        raise HTTPException(status_code=404, detail="Dispatch not found")
    
    # Enforce facility scoping for receptionists/phc_incharges
    role = claims.get("role")
    if role in ["receptionist", "phc_incharge"]:
        user_facility_id = claims.get("facility_id")
        if not user_facility_id or str(user_facility_id) != str(dispatch.facility_id):
            raise HTTPException(status_code=403, detail="Access denied: user is not scoped to this facility")
            
    # Enforce district scoping for district admins
    elif role == "district_admin":
        user_district_code = claims.get("district_code")
        facility = db.query(Facility).filter(Facility.id == dispatch.facility_id).first()
        if not facility or facility.district_code != user_district_code:
            raise HTTPException(status_code=403, detail="Access denied: facility is outside district scope")
            
    if payload.status not in ["pending", "enroute", "arrived"]:
        raise HTTPException(status_code=400, detail="Invalid status")
        
    dispatch.status = payload.status
    db.commit()
    
    # Mirror to firestore
    mirror_dispatch_to_firestore(str(dispatch.id), str(dispatch.patient_session_id), str(dispatch.facility_id), dispatch.status, dispatch.lat or 0.0, dispatch.lng or 0.0, 0)
    
    return {
        "status": "success",
        "dispatch_id": str(dispatch.id),
        "new_status": dispatch.status
    }


class WalkInPayload(BaseModel):
    patient_name: str
    age: int
    gender: str
    symptoms: str

@app.post(
    "/api/v1/receptionist/walk-in/{facility_id}",
    dependencies=[Depends(RequireRole(["receptionist", "district_admin"])), Depends(validate_facility_scope)]
)
def post_walk_in(facility_id: UUID, payload: WalkInPayload, db: Session = Depends(get_db)):
    formatted_text = f"Name: {payload.patient_name}, Age: {payload.age}, Gender: {payload.gender}, Symptoms: {payload.symptoms}"
    severity = classify_severity(payload.symptoms)
    
    patient_session = PatientSession(
        channel="walk-in",
        raw_text=formatted_text,
        language_code="en",
        confidence_score=1.0,
        severity=severity,
        created_at=datetime.utcnow()
    )
    db.add(patient_session)
    db.flush()
    
    dispatch = Dispatch(
        patient_session_id=patient_session.id,
        facility_id=facility_id,
        status="arrived",
        lat=0.0,
        lng=0.0,
        eta=datetime.utcnow()
    )
    db.add(dispatch)
    
    # Increment footfall count
    today = datetime.utcnow().date()
    footfall = db.query(FootfallLog).filter(
        FootfallLog.facility_id == facility_id,
        FootfallLog.date == today
    ).first()
    if not footfall:
        footfall = FootfallLog(
            facility_id=facility_id,
            date=today,
            count=1
        )
        db.add(footfall)
    else:
        footfall.count += 1
        
    db.commit()
    
    return {
        "status": "success",
        "patient_session_id": str(patient_session.id),
        "severity": severity
    }


# PHC In-charge specific endpoints
@app.get(
    "/api/v1/inventory/{facility_id}",
    dependencies=[Depends(RequireRole(["phc_incharge", "district_admin", "receptionist"])), Depends(validate_facility_scope)]
)
def get_inventory(facility_id: UUID, db: Session = Depends(get_db)):
    inventory_items = db.query(InventoryItem).filter(InventoryItem.facility_id == facility_id).all()
    return [
        {
            "id": str(item.id),
            "medicine_name": item.medicine_name,
            "current_stock": item.current_stock,
            "avg_daily_burn_rate": item.avg_daily_burn_rate,
            "drp_value": item.drp_value
        }
        for item in inventory_items
    ]


@app.get(
    "/api/v1/attendance/{facility_id}",
    dependencies=[Depends(RequireRole(["phc_incharge", "district_admin"])), Depends(validate_facility_scope)]
)
def get_attendance(facility_id: UUID, db: Session = Depends(get_db)):
    facility = db.query(Facility).filter(Facility.id == facility_id).first()
    if not facility:
        raise HTTPException(status_code=404, detail="Facility not found")
    
    staff_members = db.query(Staff).filter(Staff.facility_id == facility_id).all()
    today = datetime.utcnow().date()
    
    attendance_records = []
    present_count = 0
    
    for member in staff_members:
        log = db.query(AttendanceLog).filter(
            AttendanceLog.staff_id == member.id,
            AttendanceLog.date == today
        ).first()
        
        status = log.status if log else "Absent"
        if status == "Present":
            present_count += 1
            
        attendance_records.append({
            "staff_id": str(member.id),
            "name": member.name,
            "role": member.role,
            "status": status
        })
        
    return {
        "facility_id": str(facility_id),
        "sanctioned_staff": facility.sanctioned_staff or 0,
        "present_count": present_count,
        "attendance": attendance_records
    }


class RedistributionPayload(BaseModel):
    facility_id: UUID
    reason: str

@app.post(
    "/api/v1/redistribution",
    dependencies=[Depends(RequireRole(["phc_incharge", "district_admin"]))]
)
def request_redistribution(payload: RedistributionPayload, db: Session = Depends(get_db), claims: dict = Depends(get_current_user)):
    role = claims.get("role")
    if role == "phc_incharge":
        user_facility_id = claims.get("facility_id")
        if not user_facility_id or str(user_facility_id) != str(payload.facility_id):
            raise HTTPException(status_code=403, detail="Access denied: user is not scoped to this facility")
            
    facility = db.query(Facility).filter(Facility.id == payload.facility_id).first()
    if not facility:
        raise HTTPException(status_code=404, detail="Facility not found")
        
    alert = Alert(
        type="redistribution",
        facility_id=payload.facility_id,
        district_code=facility.district_code,
        status="active",
        description=payload.reason,
        created_at=datetime.utcnow()
    )
    db.add(alert)
    db.commit()
    
    mirror_alert_to_firestore(str(alert.id), "redistribution", "active", facility_id=str(payload.facility_id), district_code=facility.district_code)
    
    return {
        "status": "success",
        "alert_id": str(alert.id)
    }


# ── District Admin: List redistribution requests ──────────────────────────────
@app.get(
    "/api/v1/district-admin/redistribution-requests",
    dependencies=[Depends(RequireRole(["district_admin"]))]
)
def list_redistribution_requests(db: Session = Depends(get_db), claims: dict = Depends(get_current_user)):
    district_code = claims.get("district_code")
    if not district_code:
        raise HTTPException(status_code=403, detail="district_code not found in token")

    alerts = db.query(Alert).filter(
        Alert.type == "redistribution",
        Alert.district_code == district_code
    ).order_by(Alert.created_at.desc()).all()

    return [
        {
            "alert_id": str(a.id),
            "facility_id": str(a.facility_id) if a.facility_id else None,
            "facility_name": a.facility.name if a.facility else "Unknown",
            "status": a.status,
            "description": a.description,
            "created_at": a.created_at.isoformat() if a.created_at else None,
        }
        for a in alerts
    ]


# ── District Admin: Approve / Reject redistribution request ──────────────────
class RedistributionActionPayload(BaseModel):
    action: str  # "approved" | "rejected"

@app.patch(
    "/api/v1/redistribution/{alert_id}",
    dependencies=[Depends(RequireRole(["district_admin"]))]
)
def update_redistribution_status(
    alert_id: UUID,
    payload: RedistributionActionPayload,
    db: Session = Depends(get_db),
    claims: dict = Depends(get_current_user)
):
    district_code = claims.get("district_code")
    alert = db.query(Alert).filter(Alert.id == alert_id, Alert.type == "redistribution").first()
    if not alert:
        raise HTTPException(status_code=404, detail="Redistribution request not found")

    # Enforce district scoping
    if alert.district_code != district_code:
        raise HTTPException(status_code=403, detail="Access denied: request is outside your district scope")

    if payload.action not in ["approved", "rejected"]:
        raise HTTPException(status_code=400, detail="action must be 'approved' or 'rejected'")

    alert.status = payload.action
    db.commit()

    # Notify via Firestore mirror
    mirror_alert_to_firestore(
        str(alert.id), "redistribution", payload.action,
        facility_id=str(alert.facility_id) if alert.facility_id else None,
        district_code=district_code
    )

    return {
        "status": "success",
        "alert_id": str(alert.id),
        "new_status": alert.status
    }


# ── District Admin: Underperforming Facilities ────────────────────────────────
FSI_HIGH_THRESHOLD = 0.0005   # flags facilities with FSI above this
ATTENDANCE_LOW_THRESHOLD = 0.6  # flags if present/sanctioned < 60%

@app.get(
    "/api/v1/district-admin/underperforming",
    dependencies=[Depends(RequireRole(["district_admin"])), Depends(validate_district_scope)]
)
def get_underperforming_facilities(district_code: str, db: Session = Depends(get_db)):
    facilities = db.query(Facility).filter(Facility.district_code == district_code).all()
    today = datetime.utcnow().date()
    flagged = []

    for f in facilities:
        triggers = []

        # FSI check
        fsi_val = calculate_fsi_for_facility(f, db)
        if fsi_val > FSI_HIGH_THRESHOLD:
            triggers.append({
                "metric": "FSI",
                "value": fsi_val,
                "threshold": FSI_HIGH_THRESHOLD,
                "detail": f"FSI {fsi_val:.6f} exceeds threshold {FSI_HIGH_THRESHOLD}"
            })

        # Attendance deviation check
        staff_list = db.query(Staff).filter(Staff.facility_id == f.id).all()
        sanctioned = f.sanctioned_staff or 1
        present = 0
        for member in staff_list:
            log = db.query(AttendanceLog).filter(
                AttendanceLog.staff_id == member.id,
                AttendanceLog.date == today
            ).first()
            if log and log.status == "Present":
                present += 1

        attendance_ratio = present / sanctioned if sanctioned else 1.0
        if attendance_ratio < ATTENDANCE_LOW_THRESHOLD:
            triggers.append({
                "metric": "Attendance",
                "value": round(attendance_ratio, 3),
                "threshold": ATTENDANCE_LOW_THRESHOLD,
                "detail": f"Only {present}/{sanctioned} staff present ({attendance_ratio*100:.1f}% < {ATTENDANCE_LOW_THRESHOLD*100:.0f}%)"
            })

        if triggers:
            flagged.append({
                "facility_id": str(f.id),
                "facility_name": f.name,
                "facility_type": f.type,
                "fsi_value": fsi_val,
                "triggers": triggers
            })

    return {"district_code": district_code, "underperforming": flagged}


# ── District Admin: Attendance Deviation Report ───────────────────────────────
@app.get(
    "/api/v1/district-admin/attendance-deviation",
    dependencies=[Depends(RequireRole(["district_admin"])), Depends(validate_district_scope)]
)
def get_district_attendance_deviation(district_code: str, db: Session = Depends(get_db)):
    facilities = db.query(Facility).filter(Facility.district_code == district_code).all()
    today = datetime.utcnow().date()
    report = []

    for f in facilities:
        staff_list = db.query(Staff).filter(Staff.facility_id == f.id).all()
        sanctioned = f.sanctioned_staff or 0
        present = 0
        for member in staff_list:
            log = db.query(AttendanceLog).filter(
                AttendanceLog.staff_id == member.id,
                AttendanceLog.date == today
            ).first()
            if log and log.status == "Present":
                present += 1

        deviation = sanctioned - present
        report.append({
            "facility_id": str(f.id),
            "facility_name": f.name,
            "facility_type": f.type,
            "sanctioned_staff": sanctioned,
            "present_today": present,
            "deviation": deviation,
            "attendance_pct": round((present / sanctioned * 100) if sanctioned else 0, 1)
        })

    return {"district_code": district_code, "date": str(today), "facilities": report}


# ── District Admin: Fleet / Dispatch Status ───────────────────────────────────
@app.get(
    "/api/v1/district-admin/fleet",
    dependencies=[Depends(RequireRole(["district_admin"])), Depends(validate_district_scope)]
)
def get_district_fleet(district_code: str, db: Session = Depends(get_db)):
    facilities = db.query(Facility).filter(Facility.district_code == district_code).all()
    facility_ids = [f.id for f in facilities]
    facility_map = {str(f.id): f.name for f in facilities}

    dispatches = db.query(Dispatch).filter(Dispatch.facility_id.in_(facility_ids)).order_by(Dispatch.eta.desc()).all()

    result = {"pending": [], "enroute": [], "arrived": []}
    for d in dispatches:
        item = {
            "dispatch_id": str(d.id),
            "facility_name": facility_map.get(str(d.facility_id), "Unknown"),
            "facility_id": str(d.facility_id),
            "status": d.status,
            "eta": d.eta.isoformat() if d.eta else None,
            "symptom": d.patient_session.raw_text if d.patient_session else ""
        }
        if d.status in result:
            result[d.status].append(item)

    result["total"] = len(dispatches)
    result["district_code"] = district_code
    return result


# ── District Admin: Benchmark Comparison View ─────────────────────────────────
from reference_service import get_nfhs_data, get_datagovin_data

@app.get(
    "/api/v1/district-admin/benchmarks",
    dependencies=[Depends(RequireRole(["district_admin"])), Depends(validate_district_scope)]
)
def get_district_benchmarks(district_code: str, db: Session = Depends(get_db)):
    facilities = db.query(Facility).filter(Facility.district_code == district_code).all()
    today = datetime.utcnow().date()

    census_data = get_census_data(district_code, db)
    nfhs_data = get_nfhs_data(district_code, db)
    datagovin_data = get_datagovin_data(district_code, db)

    # Aggregate live metrics
    total_sanctioned_staff = sum(f.sanctioned_staff or 0 for f in facilities)
    total_present = 0
    for f in facilities:
        for member in db.query(Staff).filter(Staff.facility_id == f.id).all():
            log = db.query(AttendanceLog).filter(
                AttendanceLog.staff_id == member.id,
                AttendanceLog.date == today
            ).first()
            if log and log.status == "Present":
                total_present += 1

    avg_fsi = 0.0
    for f in facilities:
        avg_fsi += calculate_fsi_for_facility(f, db)
    avg_fsi = round(avg_fsi / len(facilities), 6) if facilities else 0.0

    return {
        "district_code": district_code,
        "total_facilities": len(facilities),
        "live_metrics": {
            "avg_fsi": avg_fsi,
            "total_sanctioned_staff": total_sanctioned_staff,
            "total_staff_present_today": total_present,
            "attendance_pct": round((total_present / total_sanctioned_staff * 100) if total_sanctioned_staff else 0, 1)
        },
        "census_reference": census_data or {},
        "nfhs_reference": nfhs_data or {},
        "datagovin_reference": datagovin_data or {},
        "comparison": {
            "staff_vs_benchmark": {
                "actual": total_sanctioned_staff,
                "benchmark": (datagovin_data or {}).get("sanctioned_staff_count", 0),
                "gap": total_sanctioned_staff - (datagovin_data or {}).get("sanctioned_staff_count", 0)
            },
            "seasonal_risk_weight": (nfhs_data or {}).get("seasonal_vector_weight", 1.0),
            "catchment_population": (census_data or {}).get("catchment_population", 0)
        }
    }
