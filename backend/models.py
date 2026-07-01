import uuid
from datetime import datetime
from sqlalchemy import Column, String, Float, Integer, Date, DateTime, ForeignKey, Uuid
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()

class Facility(Base):
    __tablename__ = 'facilities'

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    district_code = Column(String, nullable=False, index=True)
    name = Column(String, nullable=False)
    type = Column(String, nullable=False)  # PHC, CHC
    lat = Column(Float)
    lng = Column(Float)
    sanctioned_beds = Column(Integer, default=0)
    available_beds = Column(Integer, default=0)
    sanctioned_staff = Column(Integer, default=0)

    staff = relationship("Staff", back_populates="facility")
    inventory_items = relationship("InventoryItem", back_populates="facility")
    footfall_logs = relationship("FootfallLog", back_populates="facility")
    dispatches = relationship("Dispatch", back_populates="facility")
    alerts = relationship("Alert", back_populates="facility")


class Staff(Base):
    __tablename__ = 'staff'

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    facility_id = Column(Uuid(as_uuid=True), ForeignKey('facilities.id'), nullable=False)
    role = Column(String, nullable=False)
    name = Column(String, nullable=False)

    facility = relationship("Facility", back_populates="staff")
    attendance_logs = relationship("AttendanceLog", back_populates="staff")


class AttendanceLog(Base):
    __tablename__ = 'attendance_logs'

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    staff_id = Column(Uuid(as_uuid=True), ForeignKey('staff.id'), nullable=False)
    date = Column(Date, nullable=False)
    status = Column(String, nullable=False)  # Present, Absent, Leave

    staff = relationship("Staff", back_populates="attendance_logs")


class InventoryItem(Base):
    __tablename__ = 'inventory_items'

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    facility_id = Column(Uuid(as_uuid=True), ForeignKey('facilities.id'), nullable=False)
    medicine_name = Column(String, nullable=False)
    current_stock = Column(Integer, default=0)
    avg_daily_burn_rate = Column(Float, default=0.0)
    supply_lead_time = Column(Integer, default=0)
    drp_value = Column(Float, default=0.0)

    facility = relationship("Facility", back_populates="inventory_items")


class FootfallLog(Base):
    __tablename__ = 'footfall_logs'

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    facility_id = Column(Uuid(as_uuid=True), ForeignKey('facilities.id'), nullable=False)
    date = Column(Date, nullable=False)
    count = Column(Integer, default=0)

    facility = relationship("Facility", back_populates="footfall_logs")


class PatientSession(Base):
    __tablename__ = 'patient_sessions'

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    channel = Column(String, nullable=False)  # web, sms, whatsapp, call
    raw_text = Column(String)
    language_code = Column(String)
    confidence_score = Column(Float)
    severity = Column(String)
    created_at = Column(DateTime, default=datetime.utcnow)

    dispatch = relationship("Dispatch", back_populates="patient_session", uselist=False)


class Dispatch(Base):
    __tablename__ = 'dispatches'

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    patient_session_id = Column(Uuid(as_uuid=True), ForeignKey('patient_sessions.id'))
    facility_id = Column(Uuid(as_uuid=True), ForeignKey('facilities.id'))
    status = Column(String, nullable=False)  # pending, enroute, arrived
    lat = Column(Float)
    lng = Column(Float)
    eta = Column(DateTime)

    patient_session = relationship("PatientSession", back_populates="dispatch")
    facility = relationship("Facility", back_populates="dispatches")


class Alert(Base):
    __tablename__ = 'alerts'

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    type = Column(String, nullable=False)  # stock-out, underperforming, surge, redistribution
    facility_id = Column(Uuid(as_uuid=True), ForeignKey('facilities.id'))
    district_code = Column(String, nullable=True, index=True)
    status = Column(String, nullable=False)  # active, resolved
    description = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    facility = relationship("Facility", back_populates="alerts")


class CensusReference(Base):
    __tablename__ = 'census_reference'

    district_code = Column(String, primary_key=True, index=True)
    catchment_population = Column(Integer, default=0)
    age_cohort_under_5 = Column(Float, default=0.0)
    age_cohort_over_60 = Column(Float, default=0.0)


class NFHSReference(Base):
    __tablename__ = 'nfhs_reference'

    district_code = Column(String, primary_key=True, index=True)
    seasonal_vector_weight = Column(Float, default=0.0)
    disease_burden_indicators = Column(String, nullable=True)


class DataGovInReference(Base):
    __tablename__ = 'datagovin_reference'

    district_code = Column(String, primary_key=True, index=True)
    sanctioned_staff_count = Column(Integer, default=0)
    supply_lead_time_baseline = Column(Integer, default=0)

