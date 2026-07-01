import pytest
from uuid import uuid4
import jwt
from datetime import datetime, timedelta
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from config import settings
from main import app
from database import get_db
from models import Base, Facility, Staff, AttendanceLog, InventoryItem, Alert

TEST_DB_URL = "sqlite:///test_phc_healthify.db"
engine = create_engine(TEST_DB_URL, connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

@pytest.fixture(scope="function")
def db_session():
    Base.metadata.create_all(bind=engine)
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()

@pytest.fixture(scope="function")
def client(db_session):
    def override_get_db():
        try:
            yield db_session
        finally:
            pass
    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()

def generate_token(role: str, facility_id: str = None, district_code: str = None) -> str:
    claims = {
        "sub": f"{role}@test.com",
        "email": f"{role}@test.com",
        "role": role,
        "exp": datetime.utcnow() + timedelta(hours=1)
    }
    if facility_id:
        claims["facility_id"] = str(facility_id)
    if district_code:
        claims["district_code"] = district_code
    return jwt.encode(claims, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)

def test_inventory_endpoint(client, db_session):
    fac_id = uuid4()
    facility = Facility(
        id=fac_id,
        name="Test Bangalore PHC",
        type="PHC",
        district_code="KA-BNG"
    )
    db_session.add(facility)
    
    item = InventoryItem(
        facility_id=fac_id,
        medicine_name="Paracetamol 500mg",
        current_stock=80,
        avg_daily_burn_rate=10.5,
        supply_lead_time=7,
        drp_value=100.0
    )
    db_session.add(item)
    db_session.commit()
    
    token = generate_token("phc_incharge", facility_id=str(fac_id))
    headers = {"Authorization": f"Bearer {token}"}
    
    response = client.get(f"/api/v1/inventory/{fac_id}", headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["medicine_name"] == "Paracetamol 500mg"
    assert data[0]["current_stock"] == 80
    assert data[0]["drp_value"] == 100.0

def test_attendance_endpoint(client, db_session):
    fac_id = uuid4()
    facility = Facility(
        id=fac_id,
        name="Test Bangalore PHC",
        type="PHC",
        district_code="KA-BNG",
        sanctioned_staff=3
    )
    db_session.add(facility)
    
    staff = Staff(
        id=uuid4(),
        facility_id=fac_id,
        role="Doctor",
        name="Dr. Smith"
    )
    db_session.add(staff)
    db_session.commit()
    
    # Add attendance for today
    today = datetime.utcnow().date()
    att = AttendanceLog(
        staff_id=staff.id,
        date=today,
        status="Present"
    )
    db_session.add(att)
    db_session.commit()
    
    token = generate_token("phc_incharge", facility_id=str(fac_id))
    headers = {"Authorization": f"Bearer {token}"}
    
    response = client.get(f"/api/v1/attendance/{fac_id}", headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert data["sanctioned_staff"] == 3
    assert data["present_count"] == 1
    assert data["attendance"][0]["name"] == "Dr. Smith"
    assert data["attendance"][0]["status"] == "Present"

def test_redistribution_endpoint(client, db_session):
    fac_id = uuid4()
    facility = Facility(
        id=fac_id,
        name="Test Bangalore PHC",
        type="PHC",
        district_code="KA-BNG"
    )
    db_session.add(facility)
    db_session.commit()
    
    token = generate_token("phc_incharge", facility_id=str(fac_id))
    headers = {"Authorization": f"Bearer {token}"}
    
    response = client.post("/api/v1/redistribution", json={
        "facility_id": str(fac_id),
        "reason": "Severe doctor shortage due to high seasonal FSI"
    }, headers=headers)
    
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert "alert_id" in data
    
    # Verify Alert is created
    alert = db_session.query(Alert).filter(Alert.type == "redistribution").first()
    assert alert is not None
    assert alert.facility_id == fac_id
    assert alert.description == "Severe doctor shortage due to high seasonal FSI"
    assert alert.status == "active"
