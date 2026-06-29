import io
import uuid
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
import jwt
from datetime import datetime, timedelta

from config import settings
from database import get_db
from main import app
from models import Base, Facility, Staff, InventoryItem, FootfallLog, AttendanceLog
import voice

TEST_DATABASE_URL = "sqlite:///./test_voice_healthify.db"
engine = create_engine(TEST_DATABASE_URL, connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def override_get_db():
    try:
        db = TestingSessionLocal()
        yield db
    finally:
        db.close()

client = TestClient(app)

# Test facility, staff, inventory items
FACILITY_ID = "55555555-5555-5555-5555-555555555555"
STAFF_ID = "66666666-6666-6666-6666-666666666666"
STAFF_NAME = "Dr. Ramesh"

@pytest.fixture(scope="module", autouse=True)
def setup_db():
    app.dependency_overrides[get_db] = override_get_db
    Base.metadata.create_all(bind=engine)
    db = TestingSessionLocal()
    
    facility = Facility(
        id=uuid.UUID(FACILITY_ID),
        name="Voice Test Facility",
        type="PHC",
        district_code="KA-BNG",
        available_beds=10,
        sanctioned_beds=20
    )
    db.add(facility)
    db.commit()
    
    staff = Staff(
        id=uuid.UUID(STAFF_ID),
        facility_id=uuid.UUID(FACILITY_ID),
        role="doctor",
        name=STAFF_NAME
    )
    db.add(staff)
    
    item1 = InventoryItem(
        id=uuid.uuid4(),
        facility_id=uuid.UUID(FACILITY_ID),
        medicine_name="Paracetamol",
        current_stock=100,
        avg_daily_burn_rate=2.5,
        supply_lead_time=5
    )
    item2 = InventoryItem(
        id=uuid.uuid4(),
        facility_id=uuid.UUID(FACILITY_ID),
        medicine_name="Amoxicillin",
        current_stock=50,
        avg_daily_burn_rate=1.0,
        supply_lead_time=7
    )
    db.add_all([item1, item2])
    db.commit()
    db.close()
    
    yield
    
    Base.metadata.drop_all(bind=engine)
    app.dependency_overrides.pop(get_db, None)

def generate_token(role: str, facility_id: str) -> str:
    claims = {
        "sub": f"{role}@test.com",
        "email": f"{role}@test.com",
        "role": role,
        "facility_id": facility_id,
        "exp": datetime.utcnow() + timedelta(hours=1)
    }
    return jwt.encode(claims, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)

def test_transcribe_invalid_file_type():
    token = generate_token("receptionist", FACILITY_ID)
    headers = {"Authorization": f"Bearer {token}"}
    
    # Send a text file instead of audio
    files = {"file": ("test.txt", io.BytesIO(b"dummy audio"), "text/plain")}
    response = client.post("/api/v1/voice/transcribe", files=files, headers=headers)
    assert response.status_code == 400
    assert "Unsupported audio format" in response.json()["detail"]

def test_transcribe_unauthorized():
    files = {"file": ("test.mp3", io.BytesIO(b"dummy audio"), "audio/mpeg")}
    response = client.post("/api/v1/voice/transcribe", files=files)
    assert response.status_code == 401

def test_transcribe_stock_update_khatam(monkeypatch):
    # Mock Speech-to-Text translation
    def mock_transcribe(audio_content, explicit_language=None):
        return {
            "transcribed_text": "Paracetamol stock khatam ho gaya hai",
            "confidence_score": 0.92,
            "detected_language_code": "hi-IN"
        }
    monkeypatch.setattr(voice, "transcribe_audio", mock_transcribe)
    
    token = generate_token("receptionist", FACILITY_ID)
    headers = {"Authorization": f"Bearer {token}"}
    files = {"file": ("test.mp3", io.BytesIO(b"dummy audio"), "audio/mpeg")}
    
    response = client.post("/api/v1/voice/transcribe", files=files, headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert data["intent"] == "stock_update"
    assert data["extracted_entity"] == "Paracetamol"
    assert data["extracted_value"] == 0
    
    # Verify DB update
    db = TestingSessionLocal()
    item = db.query(InventoryItem).filter(
        InventoryItem.facility_id == uuid.UUID(FACILITY_ID),
        InventoryItem.medicine_name == "Paracetamol"
    ).first()
    assert item.current_stock == 0
    db.close()

def test_transcribe_stock_update_with_count(monkeypatch):
    def mock_transcribe(audio_content, explicit_language=None):
        return {
            "transcribed_text": "Amoxicillin stock is 45 packages",
            "confidence_score": 0.95,
            "detected_language_code": "en-IN"
        }
    monkeypatch.setattr(voice, "transcribe_audio", mock_transcribe)
    
    token = generate_token("phc_incharge", FACILITY_ID)
    headers = {"Authorization": f"Bearer {token}"}
    files = {"file": ("test.wav", io.BytesIO(b"dummy audio"), "audio/wav")}
    
    response = client.post("/api/v1/voice/transcribe", files=files, headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert data["intent"] == "stock_update"
    assert data["extracted_entity"] == "Amoxicillin"
    assert data["extracted_value"] == 45
    
    # Verify DB update
    db = TestingSessionLocal()
    item = db.query(InventoryItem).filter(
        InventoryItem.facility_id == uuid.UUID(FACILITY_ID),
        InventoryItem.medicine_name == "Amoxicillin"
    ).first()
    assert item.current_stock == 45
    db.close()

def test_transcribe_footfall_count(monkeypatch):
    def mock_transcribe(audio_content, explicit_language=None):
        return {
            "transcribed_text": "OPD footfall is 120 patients today",
            "confidence_score": 0.88,
            "detected_language_code": "en-US"
        }
    monkeypatch.setattr(voice, "transcribe_audio", mock_transcribe)
    
    token = generate_token("receptionist", FACILITY_ID)
    headers = {"Authorization": f"Bearer {token}"}
    files = {"file": ("test.m4a", io.BytesIO(b"dummy audio"), "audio/mp4")}
    
    response = client.post("/api/v1/voice/transcribe", files=files, headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert data["intent"] == "footfall_count"
    assert data["extracted_entity"] == "footfall"
    assert data["extracted_value"] == 120
    
    # Verify DB update
    db = TestingSessionLocal()
    log = db.query(FootfallLog).filter(
        FootfallLog.facility_id == uuid.UUID(FACILITY_ID)
    ).first()
    assert log.count == 120
    db.close()

def test_transcribe_attendance_log(monkeypatch):
    def mock_transcribe(audio_content, explicit_language=None):
        return {
            "transcribed_text": "Dr. Ramesh is present",
            "confidence_score": 0.97,
            "detected_language_code": "en-IN"
        }
    monkeypatch.setattr(voice, "transcribe_audio", mock_transcribe)
    
    token = generate_token("phc_incharge", FACILITY_ID)
    headers = {"Authorization": f"Bearer {token}"}
    files = {"file": ("test.ogg", io.BytesIO(b"dummy audio"), "audio/ogg")}
    
    response = client.post("/api/v1/voice/transcribe", files=files, headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert data["intent"] == "attendance_log"
    assert data["extracted_entity"] == STAFF_NAME
    assert data["extracted_value"] == "Present"
    
    # Verify DB update
    db = TestingSessionLocal()
    log = db.query(AttendanceLog).filter(
        AttendanceLog.staff_id == uuid.UUID(STAFF_ID)
    ).first()
    assert log.status == "Present"
    db.close()

def test_transcribe_unclassified_fallback(monkeypatch):
    def mock_transcribe(audio_content, explicit_language=None):
        return {
            "transcribed_text": "hello testing routing",
            "confidence_score": 0.75,
            "detected_language_code": "en-US"
        }
    monkeypatch.setattr(voice, "transcribe_audio", mock_transcribe)
    
    token = generate_token("receptionist", FACILITY_ID)
    headers = {"Authorization": f"Bearer {token}"}
    files = {"file": ("test.wav", io.BytesIO(b"dummy audio"), "audio/wav")}
    
    response = client.post("/api/v1/voice/transcribe", files=files, headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert data["intent"] == "unclassified"
    assert data["extracted_entity"] is None
    assert data["extracted_value"] is None

def test_transcribe_explicit_language_passed(monkeypatch):
    passed_lang = []
    
    def mock_transcribe(audio_content, explicit_language=None):
        passed_lang.append(explicit_language)
        return {
            "transcribed_text": "Amoxicillin stock count is 55",
            "confidence_score": 0.99,
            "detected_language_code": explicit_language or "en-IN"
        }
    monkeypatch.setattr(voice, "transcribe_audio", mock_transcribe)
    
    token = generate_token("phc_incharge", FACILITY_ID)
    headers = {"Authorization": f"Bearer {token}"}
    files = {"file": ("test.wav", io.BytesIO(b"dummy audio"), "audio/wav")}
    data = {"language_code": "hi-IN"}
    
    response = client.post("/api/v1/voice/transcribe", files=files, data=data, headers=headers)
    assert response.status_code == 200
    assert passed_lang == ["hi-IN"]
