import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
import jwt
from datetime import datetime, timedelta
import uuid

from config import settings
from database import get_db
from main import app
from models import Base, Facility, Staff, InventoryItem, FootfallLog

# Setup database for tests
TEST_DATABASE_URL = "sqlite:///./test_healthify.db"
engine = create_engine(TEST_DATABASE_URL, connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Override get_db dependency
def override_get_db():
    try:
        db = TestingSessionLocal()
        yield db
    finally:
        db.close()

client = TestClient(app)

@pytest.fixture(scope="module", autouse=True)
def setup_db():
    app.dependency_overrides[get_db] = override_get_db
    Base.metadata.create_all(bind=engine)
    db = TestingSessionLocal()
    
    # Seed data for testing
    # District 1: KA-BNG
    # District 2: MH-MUM
    f1 = Facility(
        id=uuid.UUID("11111111-1111-1111-1111-111111111111"),
        name="Test Facility 1 (KA)",
        type="PHC",
        district_code="KA-BNG",
        available_beds=10,
        sanctioned_beds=20
    )
    f2 = Facility(
        id=uuid.UUID("22222222-2222-2222-2222-222222222222"),
        name="Test Facility 2 (KA)",
        type="CHC",
        district_code="KA-BNG",
        available_beds=5,
        sanctioned_beds=50
    )
    f3 = Facility(
        id=uuid.UUID("33333333-3333-3333-3333-333333333333"),
        name="Test Facility 3 (MH)",
        type="PHC",
        district_code="MH-MUM",
        available_beds=15,
        sanctioned_beds=30
    )
    
    db.add_all([f1, f2, f3])
    db.commit()
    db.close()
    
    yield
    
    Base.metadata.drop_all(bind=engine)
    app.dependency_overrides.pop(get_db, None)

def generate_test_token(role: str, facility_id: str = None, district_code: str = None) -> str:
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

def test_health_check():
    response = client.get("/health-check")
    assert response.status_code == 200
    assert response.json()["status"] == "healthy"

def test_unauthenticated_protected_endpoint():
    response = client.get("/api/v1/receptionist/data/11111111-1111-1111-1111-111111111111")
    assert response.status_code == 401  # HTTPBearer returns 401 on missing credentials

def test_receptionist_access_matching_facility():
    # Receptionist for Facility 1 tries to access Facility 1
    token = generate_test_token("receptionist", facility_id="11111111-1111-1111-1111-111111111111")
    headers = {"Authorization": f"Bearer {token}"}
    response = client.get("/api/v1/receptionist/data/11111111-1111-1111-1111-111111111111", headers=headers)
    assert response.status_code == 200
    assert response.json()["facility_name"] == "Test Facility 1 (KA)"

def test_receptionist_access_mismatching_facility():
    # Receptionist for Facility 1 tries to access Facility 2
    token = generate_test_token("receptionist", facility_id="11111111-1111-1111-1111-111111111111")
    headers = {"Authorization": f"Bearer {token}"}
    response = client.get("/api/v1/receptionist/data/22222222-2222-2222-2222-222222222222", headers=headers)
    assert response.status_code == 403
    assert "user is not scoped to this facility" in response.json()["detail"]

def test_receptionist_access_phc_incharge_endpoint():
    # Receptionists shouldn't access PHC in-charge endpoint
    token = generate_test_token("receptionist", facility_id="11111111-1111-1111-1111-111111111111")
    headers = {"Authorization": f"Bearer {token}"}
    response = client.get("/api/v1/phc-incharge/data/11111111-1111-1111-1111-111111111111", headers=headers)
    assert response.status_code == 403

def test_phc_incharge_access_matching_facility():
    token = generate_test_token("phc_incharge", facility_id="11111111-1111-1111-1111-111111111111")
    headers = {"Authorization": f"Bearer {token}"}
    response = client.get("/api/v1/phc-incharge/data/11111111-1111-1111-1111-111111111111", headers=headers)
    assert response.status_code == 200
    assert response.json()["facility_name"] == "Test Facility 1 (KA)"

def test_district_admin_access_facility_in_district():
    # Admin for KA-BNG tries to access Facility 1 (KA-BNG)
    token = generate_test_token("district_admin", district_code="KA-BNG")
    headers = {"Authorization": f"Bearer {token}"}
    response = client.get("/api/v1/receptionist/data/11111111-1111-1111-1111-111111111111", headers=headers)
    assert response.status_code == 200
    
    # Admin for KA-BNG tries to access PHC in-charge data for Facility 2 (KA-BNG)
    response = client.get("/api/v1/phc-incharge/data/22222222-2222-2222-2222-222222222222", headers=headers)
    assert response.status_code == 200

def test_district_admin_access_facility_outside_district():
    # Admin for KA-BNG tries to access Facility 3 (MH-MUM)
    token = generate_test_token("district_admin", district_code="KA-BNG")
    headers = {"Authorization": f"Bearer {token}"}
    response = client.get("/api/v1/receptionist/data/33333333-3333-3333-3333-333333333333", headers=headers)
    assert response.status_code == 403
    assert "facility is outside your district scope" in response.json()["detail"]

def test_district_admin_access_matching_district_aggregate():
    token = generate_test_token("district_admin", district_code="KA-BNG")
    headers = {"Authorization": f"Bearer {token}"}
    response = client.get("/api/v1/district-admin/data/KA-BNG", headers=headers)
    assert response.status_code == 200
    assert response.json()["total_facilities"] == 2

def test_district_admin_access_mismatching_district_aggregate():
    token = generate_test_token("district_admin", district_code="KA-BNG")
    headers = {"Authorization": f"Bearer {token}"}
    response = client.get("/api/v1/district-admin/data/MH-MUM", headers=headers)
    assert response.status_code == 403
    assert "district is outside your admin scope" in response.json()["detail"]
