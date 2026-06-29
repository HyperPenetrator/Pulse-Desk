import os
import sys
import pytest
from uuid import uuid4
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Set path to import models and config
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))
from models import Base, Facility, PatientSession, Dispatch, Alert
from main import app
from database import get_db

TEST_DB_URL = "sqlite:///test_intake_healthify.db"
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
        if os.path.exists("test_intake_healthify.db"):
            try:
                os.remove("test_intake_healthify.db")
            except OSError:
                pass

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


def test_intake_non_emergency(client, db_session):
    # Verify non-emergency symptom
    response = client.post("/api/v1/intake", json={
        "symptom": "Mild cough and running nose for two days",
        "lat": 12.9716,
        "lng": 77.5946
    })
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "triage"
    assert data["severity"] == "non-emergency"
    assert "Non-emergency detected" in data["message"]

    # Verify PatientSession is saved
    session = db_session.query(PatientSession).first()
    assert session is not None
    assert session.severity == "non-emergency"
    assert session.channel == "web"


def test_intake_emergency_with_facility_capacity(client, db_session):
    # Seed a facility with available beds near Bangalore (lat=12.97, lng=77.59)
    facility = Facility(
        id=uuid4(),
        name="Bangalore Test PHC",
        type="PHC",
        district_code="KA-BNG",
        lat=12.9710,
        lng=77.5940,
        sanctioned_beds=50,
        available_beds=5,
        sanctioned_staff=10
    )
    db_session.add(facility)
    db_session.commit()

    # Send emergency symptom (e.g. "chest pain")
    response = client.post("/api/v1/intake", json={
        "symptom": "Severe chest pain and breathing difficulty",
        "lat": 12.9716,
        "lng": 77.5946
    })
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "dispatched"
    assert data["severity"] == "emergency"
    assert data["facility_name"] == "Bangalore Test PHC"
    assert "eta" in data

    # Verify Dispatch and Alert records
    dispatch = db_session.query(Dispatch).first()
    assert dispatch is not None
    assert dispatch.facility_id == facility.id
    assert dispatch.status == "pending"

    alert = db_session.query(Alert).first()
    assert alert is not None
    assert alert.type == "surge"
    assert alert.facility_id == facility.id
    assert alert.status == "active"


def test_intake_emergency_no_beds_escalation(client, db_session):
    # Seed a facility near the patient but with 0 available beds
    facility = Facility(
        id=uuid4(),
        name="Bangalore Busy PHC",
        type="PHC",
        district_code="KA-BNG",
        lat=12.9710,
        lng=77.5940,
        sanctioned_beds=50,
        available_beds=0,
        sanctioned_staff=10
    )
    db_session.add(facility)
    db_session.commit()

    response = client.post("/api/v1/intake", json={
        "symptom": "Unconscious after an accident",
        "lat": 12.9716,
        "lng": 77.5946
    })
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "escalated"
    assert data["severity"] == "emergency"
    assert "Escalated to district-admin" in data["message"]
    assert data["district_code"] == "KA-BNG"

    # Verify Alert is created with facility_id = None and district_code = KA-BNG
    alert = db_session.query(Alert).first()
    assert alert is not None
    assert alert.type == "surge"
    assert alert.facility_id is None
    assert alert.district_code == "KA-BNG"
    assert alert.status == "active"

    # Verify no Dispatch was created
    dispatch = db_session.query(Dispatch).first()
    assert dispatch is None


def test_intake_emergency_out_of_radius_escalation(client, db_session):
    # Seed a facility with capacity but far away (Mumbai is > 800km from Bangalore)
    facility = Facility(
        id=uuid4(),
        name="Mumbai PHC",
        type="PHC",
        district_code="MH-MUM",
        lat=19.0760,
        lng=72.8777,
        sanctioned_beds=50,
        available_beds=5,
        sanctioned_staff=10
    )
    db_session.add(facility)
    db_session.commit()

    # Patient is in Bangalore (lat=12.97, lng=77.59), Mumbai is too far (> 50 km)
    response = client.post("/api/v1/intake", json={
        "symptom": "Heart attack symptoms",
        "lat": 12.9716,
        "lng": 77.5946
    })
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "escalated"
    assert data["severity"] == "emergency"
    assert "Escalated to district-admin" in data["message"]
    assert data["district_code"] == "MH-MUM"

    # Verify Alert is escalated (facility_id = None)
    alert = db_session.query(Alert).first()
    assert alert is not None
    assert alert.facility_id is None
    assert alert.district_code == "MH-MUM"
