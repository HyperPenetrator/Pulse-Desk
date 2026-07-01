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
from models import Base, Facility, Dispatch, PatientSession, Alert

TEST_DB_URL = "sqlite:///test_receptionist_healthify.db"
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

def test_walk_in_registration(client, db_session):
    facility_id = uuid4()
    facility = Facility(
        id=facility_id,
        name="Test CHC",
        type="CHC",
        district_code="KA-BNG",
        lat=12.9,
        lng=77.5,
        available_beds=5,
        sanctioned_beds=20
    )
    db_session.add(facility)
    db_session.commit()

    token = generate_token("receptionist", facility_id=str(facility_id))
    headers = {"Authorization": f"Bearer {token}"}

    response = client.post(f"/api/v1/receptionist/walk-in/{facility_id}", json={
        "patient_name": "Ramesh Kumar",
        "age": 34,
        "gender": "Male",
        "symptoms": "Mild fever and body pain"
    }, headers=headers)

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert "patient_session_id" in data

    # Verify PatientSession in DB
    session = db_session.query(PatientSession).filter(PatientSession.channel == "walk-in").first()
    assert session is not None
    assert "Ramesh Kumar" in session.raw_text
    assert session.severity == "non-emergency"

    # Verify Dispatch created with status arrived
    dispatch = db_session.query(Dispatch).filter(Dispatch.patient_session_id == session.id).first()
    assert dispatch is not None
    assert dispatch.status == "arrived"
    assert dispatch.facility_id == facility_id

def test_dispatch_patch(client, db_session):
    facility_id = uuid4()
    facility = Facility(
        id=facility_id,
        name="Test PHC",
        type="PHC",
        district_code="KA-BNG",
        lat=12.9,
        lng=77.5,
        available_beds=5,
        sanctioned_beds=20
    )
    db_session.add(facility)
    db_session.commit()

    patient_session = PatientSession(
        channel="web",
        raw_text="Chest pain",
        severity="emergency"
    )
    db_session.add(patient_session)
    db_session.commit()

    dispatch = Dispatch(
        patient_session_id=patient_session.id,
        facility_id=facility_id,
        status="pending",
        lat=12.9,
        lng=77.5,
        eta=datetime.utcnow()
    )
    db_session.add(dispatch)
    db_session.commit()

    # Try patching with a receptionist token for the SAME facility
    token = generate_token("receptionist", facility_id=str(facility_id))
    headers = {"Authorization": f"Bearer {token}"}
    response = client.patch(f"/api/v1/dispatch/{dispatch.id}", json={"status": "enroute"}, headers=headers)
    assert response.status_code == 200
    assert response.json()["new_status"] == "enroute"

    # Verify DB update
    db_session.refresh(dispatch)
    assert dispatch.status == "enroute"

    # Try patching with receptionist for a DIFFERENT facility (should fail)
    other_facility_id = uuid4()
    bad_token = generate_token("receptionist", facility_id=str(other_facility_id))
    bad_headers = {"Authorization": f"Bearer {bad_token}"}
    response2 = client.patch(f"/api/v1/dispatch/{dispatch.id}", json={"status": "arrived"}, headers=bad_headers)
    assert response2.status_code == 403

def test_mock_transcribe_fallback(client, db_session):
    facility_id = uuid4()
    token = generate_token("receptionist", facility_id=str(facility_id))
    headers = {"Authorization": f"Bearer {token}"}

    # Post with mock text to voice transcribe endpoint
    files = {"file": ("mock.wav", b"fake wav audio content", "audio/wav")}
    data = {"mock_text": "OPD footfall is 150 patients today"}

    response = client.post("/api/v1/voice/transcribe", files=files, data=data, headers=headers)
    assert response.status_code == 200
    res_data = response.json()
    assert res_data["transcribed_text"] == "OPD footfall is 150 patients today"
    assert res_data["intent"] == "footfall_count"
    assert res_data["extracted_value"] == 150
