"""
Tests for the District Admin Dashboard endpoints (Stage 9).
Covers:
  - FSI district endpoint scoped to correct district
  - Redistribution list scoped to district
  - Approve/reject redistribution updates status
  - Cross-district access blocked with 403
  - Underperforming facilities returns flagged list
  - Attendance deviation report
  - Fleet status endpoint
  - Benchmark comparison view
"""
import pytest
import jwt
from datetime import datetime, timedelta, date
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import sys, os
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from main import app
from models import Base, Facility, Staff, AttendanceLog, InventoryItem, FootfallLog, Alert, Dispatch, PatientSession, CensusReference, NFHSReference, DataGovInReference
from database import get_db

# ── Test database setup ───────────────────────────────────────────────────────
SQLALCHEMY_TEST_URL = "sqlite:///./test_district_admin_healthify.db"
test_engine = create_engine(SQLALCHEMY_TEST_URL, connect_args={"check_same_thread": False})
TestSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)

Base.metadata.create_all(bind=test_engine)

def override_get_db():
    db = TestSessionLocal()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture(scope="module", autouse=True)
def setup_overrides():
    app.dependency_overrides[get_db] = override_get_db
    yield
    app.dependency_overrides.clear()

client = TestClient(app)

JWT_SECRET = "supersecretkeyforlocaldevelopment"
JWT_ALGORITHM = "HS256"

def make_token(role: str, district_code: str = None, facility_id: str = None) -> str:
    claims = {
        "sub": f"{role}@test.gov.in",
        "email": f"{role}@test.gov.in",
        "role": role,
        "exp": datetime.utcnow() + timedelta(hours=1)
    }
    if district_code:
        claims["district_code"] = district_code
    if facility_id:
        claims["facility_id"] = facility_id
    return jwt.encode(claims, JWT_SECRET, algorithm=JWT_ALGORITHM)


# ── Fixtures ──────────────────────────────────────────────────────────────────
@pytest.fixture(scope="module")
def seeded_db():
    """Seed a fresh test DB with two districts of facilities."""
    Base.metadata.drop_all(bind=test_engine)
    Base.metadata.create_all(bind=test_engine)
    db = TestSessionLocal()
    try:
        # Two districts
        fac_a = Facility(district_code="DIST-A", name="Facility Alpha", type="PHC",
                         lat=12.9, lng=77.5, sanctioned_beds=30, available_beds=10, sanctioned_staff=20)
        fac_b = Facility(district_code="DIST-A", name="Facility Beta", type="CHC",
                         lat=12.95, lng=77.6, sanctioned_beds=50, available_beds=5, sanctioned_staff=35)
        fac_c = Facility(district_code="DIST-B", name="Facility Gamma", type="PHC",
                         lat=19.0, lng=72.8, sanctioned_beds=40, available_beds=8, sanctioned_staff=25)
        db.add_all([fac_a, fac_b, fac_c])
        db.commit()

        # Reference data
        db.add(CensusReference(district_code="DIST-A", catchment_population=200000, age_cohort_under_5=0.12, age_cohort_over_60=0.09))
        db.add(NFHSReference(district_code="DIST-A", seasonal_vector_weight=1.1, disease_burden_indicators="malaria"))
        db.add(DataGovInReference(district_code="DIST-A", sanctioned_staff_count=40, supply_lead_time_baseline=7))
        db.commit()

        # Staff for DIST-A
        today = date.today()
        staff_list = []
        for fac in [fac_a, fac_b]:
            for i in range(4):
                s = Staff(facility_id=fac.id, role="Doctor", name=f"Dr. Test {i}")
                db.add(s)
                staff_list.append((s, fac))
        db.commit()

        # Attendance: only 1 of 4 present for each (triggers low-attendance flag)
        for idx, (s, fac) in enumerate(staff_list):
            status = "Present" if idx % 4 == 0 else "Absent"
            db.add(AttendanceLog(staff_id=s.id, date=today, status=status))
        db.commit()

        # Footfall for DIST-A facilities (will drive FSI)
        for fac in [fac_a, fac_b]:
            db.add(FootfallLog(facility_id=fac.id, date=today, count=150))
        db.commit()

        # Active redistribution alert in DIST-A
        redist = Alert(
            type="redistribution",
            facility_id=fac_a.id,
            district_code="DIST-A",
            status="active",
            description="Need more Paracetamol",
            created_at=datetime.utcnow()
        )
        db.add(redist)

        # Redistribution alert in DIST-B (should NOT be visible to DIST-A admin)
        redist_b = Alert(
            type="redistribution",
            facility_id=fac_c.id,
            district_code="DIST-B",
            status="active",
            description="DIST-B request",
            created_at=datetime.utcnow()
        )
        db.add(redist_b)
        db.commit()

        # Dispatch for DIST-A
        ps = PatientSession(channel="web", raw_text="chest pain", severity="emergency",
                            language_code="en", confidence_score=1.0, created_at=datetime.utcnow())
        db.add(ps)
        db.commit()
        d = Dispatch(patient_session_id=ps.id, facility_id=fac_a.id, status="pending",
                     lat=12.9, lng=77.5, eta=datetime.utcnow() + timedelta(minutes=10))
        db.add(d)
        db.commit()

        yield db, fac_a, fac_b, fac_c, redist, redist_b
    finally:
        db.close()


# ── Tests ─────────────────────────────────────────────────────────────────────

class TestFSIDistrictEndpoint:
    def test_returns_only_own_district(self, seeded_db):
        _, fac_a, fac_b, fac_c, _, _ = seeded_db
        token = make_token("district_admin", district_code="DIST-A")
        resp = client.get("/api/v1/fsi/district/DIST-A", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["district_code"] == "DIST-A"
        facility_names = [f["facility_name"] for f in data["facilities"]]
        assert "Facility Alpha" in facility_names
        assert "Facility Beta" in facility_names
        assert "Facility Gamma" not in facility_names

    def test_cross_district_fsi_blocked(self, seeded_db):
        token = make_token("district_admin", district_code="DIST-B")
        resp = client.get("/api/v1/fsi/district/DIST-A", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 403

    def test_non_admin_fsi_district_blocked(self, seeded_db):
        _, fac_a, *_ = seeded_db
        token = make_token("phc_incharge", facility_id=str(fac_a.id))
        resp = client.get("/api/v1/fsi/district/DIST-A", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 403


class TestRedistributionRequests:
    def test_list_scoped_to_district(self, seeded_db):
        _, fac_a, fac_b, fac_c, redist, redist_b = seeded_db
        token = make_token("district_admin", district_code="DIST-A")
        resp = client.get("/api/v1/district-admin/redistribution-requests",
                          headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200
        data = resp.json()
        ids = [r["alert_id"] for r in data]
        assert str(redist.id) in ids
        assert str(redist_b.id) not in ids, "DIST-B alert must not appear for DIST-A admin"

    def test_approve_redistribution(self, seeded_db):
        _, fac_a, _, _, redist, _ = seeded_db
        token = make_token("district_admin", district_code="DIST-A")
        resp = client.patch(
            f"/api/v1/redistribution/{redist.id}",
            json={"action": "approved"},
            headers={"Authorization": f"Bearer {token}"}
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["new_status"] == "approved"

    def test_reject_redistribution(self, seeded_db):
        _, fac_a, _, _, _, redist_b = seeded_db
        # Create a new alert for DIST-A to reject
        db = TestSessionLocal()
        new_alert = Alert(
            type="redistribution", facility_id=fac_a.id, district_code="DIST-A",
            status="active", description="reject-me", created_at=datetime.utcnow()
        )
        db.add(new_alert)
        db.commit()
        alert_id = new_alert.id
        db.close()

        token = make_token("district_admin", district_code="DIST-A")
        resp = client.patch(
            f"/api/v1/redistribution/{alert_id}",
            json={"action": "rejected"},
            headers={"Authorization": f"Bearer {token}"}
        )
        assert resp.status_code == 200
        assert resp.json()["new_status"] == "rejected"

    def test_cross_district_approve_blocked(self, seeded_db):
        _, _, _, _, _, redist_b = seeded_db
        # DIST-A admin tries to approve DIST-B's request
        token = make_token("district_admin", district_code="DIST-A")
        resp = client.patch(
            f"/api/v1/redistribution/{redist_b.id}",
            json={"action": "approved"},
            headers={"Authorization": f"Bearer {token}"}
        )
        assert resp.status_code == 403

    def test_invalid_action_rejected(self, seeded_db):
        _, fac_a, _, _, redist, _ = seeded_db
        db = TestSessionLocal()
        new_alert = Alert(
            type="redistribution", facility_id=fac_a.id, district_code="DIST-A",
            status="active", description="invalid-action-test", created_at=datetime.utcnow()
        )
        db.add(new_alert)
        db.commit()
        alert_id = new_alert.id
        db.close()

        token = make_token("district_admin", district_code="DIST-A")
        resp = client.patch(
            f"/api/v1/redistribution/{alert_id}",
            json={"action": "maybe"},
            headers={"Authorization": f"Bearer {token}"}
        )
        assert resp.status_code == 400


class TestUnderperformingFacilities:
    def test_returns_flagged_list(self, seeded_db):
        token = make_token("district_admin", district_code="DIST-A")
        resp = client.get("/api/v1/district-admin/underperforming?district_code=DIST-A",
                          headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200
        data = resp.json()
        assert "underperforming" in data
        # With 1/4 present → 25% < 60% threshold, both DIST-A facilities should be flagged
        flagged_names = [f["facility_name"] for f in data["underperforming"]]
        assert len(flagged_names) >= 1

    def test_cross_district_underperforming_blocked(self, seeded_db):
        token = make_token("district_admin", district_code="DIST-B")
        resp = client.get("/api/v1/district-admin/underperforming?district_code=DIST-A",
                          headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 403


class TestAttendanceDeviationReport:
    def test_returns_all_district_facilities(self, seeded_db):
        token = make_token("district_admin", district_code="DIST-A")
        resp = client.get("/api/v1/district-admin/attendance-deviation?district_code=DIST-A",
                          headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["district_code"] == "DIST-A"
        facility_names = [f["facility_name"] for f in data["facilities"]]
        assert "Facility Alpha" in facility_names
        assert "Facility Beta" in facility_names
        assert "Facility Gamma" not in facility_names

    def test_deviation_cross_district_blocked(self, seeded_db):
        token = make_token("district_admin", district_code="DIST-B")
        resp = client.get("/api/v1/district-admin/attendance-deviation?district_code=DIST-A",
                          headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 403


class TestFleetStatus:
    def test_fleet_returns_dispatches(self, seeded_db):
        token = make_token("district_admin", district_code="DIST-A")
        resp = client.get("/api/v1/district-admin/fleet?district_code=DIST-A",
                          headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200
        data = resp.json()
        assert "pending" in data
        assert "enroute" in data
        assert "arrived" in data
        assert data["district_code"] == "DIST-A"
        # The seeded dispatch is in pending state
        assert any(d["facility_name"] == "Facility Alpha" for d in data["pending"])

    def test_fleet_cross_district_blocked(self, seeded_db):
        token = make_token("district_admin", district_code="DIST-B")
        resp = client.get("/api/v1/district-admin/fleet?district_code=DIST-A",
                          headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 403


class TestBenchmarks:
    def test_benchmarks_returns_reference_data(self, seeded_db):
        token = make_token("district_admin", district_code="DIST-A")
        resp = client.get("/api/v1/district-admin/benchmarks?district_code=DIST-A",
                          headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["district_code"] == "DIST-A"
        assert "live_metrics" in data
        assert "census_reference" in data
        assert data["census_reference"].get("catchment_population") == 200000
        assert "comparison" in data

    def test_benchmarks_cross_district_blocked(self, seeded_db):
        token = make_token("district_admin", district_code="DIST-B")
        resp = client.get("/api/v1/district-admin/benchmarks?district_code=DIST-A",
                          headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 403
