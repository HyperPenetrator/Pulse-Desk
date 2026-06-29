import os
import sys
import pytest
from uuid import uuid4
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Set path to import models and config
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))
from models import Base, Facility, FootfallLog, InventoryItem, Alert, CensusReference, NFHSReference, DataGovInReference
from main import app
from database import get_db
from cron_jobs import recompute_drp_and_alerts

# Setup temporary test database
TEST_DB_URL = "sqlite:///test_analytics_healthify.db"
engine = create_engine(TEST_DB_URL, connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

@pytest.fixture(scope="module")
def db_session():
    Base.metadata.create_all(bind=engine)
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()
        if os.path.exists("test_analytics_healthify.db"):
            os.remove("test_analytics_healthify.db")

@pytest.fixture(scope="module")
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


def test_fsi_and_drp_formulas(db_session):
    # 1. Seed Census Reference
    census_ref = CensusReference(
        district_code="KA-BNG",
        catchment_population=150000,
        age_cohort_under_5=0.12,
        age_cohort_over_60=0.08
    )
    db_session.add(census_ref)
    
    # 2. Seed NFHS Reference
    nfhs_ref = NFHSReference(
        district_code="KA-BNG",
        seasonal_vector_weight=12.5,
        disease_burden_indicators='{"malaria_prevalence": 0.02}'
    )
    db_session.add(nfhs_ref)
    db_session.commit()
    
    # 3. Create Facility with Sanctioned Beds = 25
    facility = Facility(
        id=uuid4(),
        district_code="KA-BNG",
        name="Test Bangalore PHC",
        type="PHC",
        sanctioned_beds=25,
        available_beds=20
    )
    db_session.add(facility)
    
    # 4. Create Footfall Log with count = 150
    from datetime import date
    footfall = FootfallLog(
        facility_id=facility.id,
        date=date.today(),
        count=150
    )
    db_session.add(footfall)
    db_session.commit()
    
    # --- HAND-CALCULATED FSI TEST ---
    # Formula: FSI = Footfall / (Catchment Population * Sanctioned Beds)
    # Values: 150 / (150,000 * 25) = 150 / 3,750,000 = 0.00004
    from main import calculate_fsi_for_facility
    calculated_fsi = calculate_fsi_for_facility(facility, db_session)
    assert calculated_fsi == 0.00004
    
    # --- HAND-CALCULATED DRP TEST ---
    # Formula: DRP = (Daily Burn Rate * Lead Time) + NFHS Weight
    # Item 1: Burn rate = 10.5, Lead time = 7, NFHS weight = 12.5
    # Calculated DRP = (10.5 * 7) + 12.5 = 73.5 + 12.5 = 86.0
    item1 = InventoryItem(
        facility_id=facility.id,
        medicine_name="Paracetamol 500mg",
        current_stock=80,  # Below DRP (86.0) -> should trigger alert
        avg_daily_burn_rate=10.5,
        supply_lead_time=7,
        drp_value=0.0
    )
    
    # Item 2: Burn rate = 5.2, Lead time = 5, NFHS weight = 12.5
    # Calculated DRP = (5.2 * 5) + 12.5 = 26.0 + 12.5 = 38.5
    item2 = InventoryItem(
        facility_id=facility.id,
        medicine_name="Amoxicillin 250mg",
        current_stock=40,  # Above DRP (38.5) -> should NOT trigger alert
        avg_daily_burn_rate=5.2,
        supply_lead_time=5,
        drp_value=0.0
    )
    
    db_session.add(item1)
    db_session.add(item2)
    db_session.commit()
    
    # Run cron job to recalculate DRP and alerts
    job_result = recompute_drp_and_alerts(db_session)
    
    # Refresh item records
    db_session.refresh(item1)
    db_session.refresh(item2)
    
    # Assert DRP values match expected hand-calculated values
    assert item1.drp_value == 86.0
    assert item2.drp_value == 38.5
    
    # Assert Alerts
    assert job_result["new_alerts_triggered"] == 1
    
    # Assert alert exists for facility
    alert = db_session.query(Alert).filter(Alert.facility_id == facility.id, Alert.type == "stock-out").first()
    assert alert is not None
    assert alert.status == "active"


def test_api_endpoints(client, db_session):
    # Retrieve facility ID
    facility = db_session.query(Facility).first()
    assert facility is not None
    
    # Generate token with receptionist role scoped to facility
    import jwt
    from config import settings
    from datetime import datetime, timedelta
    
    claims = {
        "sub": "receptionist@swasthyagrid.gov.in",
        "email": "receptionist@swasthyagrid.gov.in",
        "role": "receptionist",
        "facility_id": str(facility.id),
        "exp": datetime.utcnow() + timedelta(hours=1)
    }
    token = jwt.encode(claims, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)
    headers = {"Authorization": f"Bearer {token}"}
    
    # Test GET /api/v1/fsi/{facility_id}
    response = client.get(f"/api/v1/fsi/{facility.id}", headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert data["fsi_value"] == 0.00004
    assert data["real_time_daily_footfall"] == 150
    assert data["census_catchment_population"] == 150000
    
    # Test GET /api/v1/fsi/district/{district_code} (District Admin role required)
    admin_claims = {
        "sub": "admin@swasthyagrid.gov.in",
        "email": "admin@swasthyagrid.gov.in",
        "role": "district_admin",
        "district_code": "KA-BNG",
        "exp": datetime.utcnow() + timedelta(hours=1)
    }
    admin_token = jwt.encode(admin_claims, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)
    admin_headers = {"Authorization": f"Bearer {admin_token}"}
    
    response = client.get("/api/v1/fsi/district/KA-BNG", headers=admin_headers)
    assert response.status_code == 200
    district_data = response.json()
    assert district_data["district_code"] == "KA-BNG"
    assert len(district_data["facilities"]) == 1
    assert district_data["facilities"][0]["fsi_value"] == 0.00004
