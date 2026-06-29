import os
import sys
import random
from datetime import datetime, timedelta
from faker import Faker
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))
from models import Base, Facility, Staff, AttendanceLog, InventoryItem, FootfallLog

fake = Faker('en_IN')

# Database setup
engine = create_engine('sqlite:///healthify.db')
Session = sessionmaker(bind=engine)
session = Session()

def run_seed():
    print("Seeding database...")
    
    # 2 Districts
    districts = ['KA-BNG', 'MH-MUM']
    
    # 5 Facilities across the 2 districts
    facilities_data = [
        {"name": "Bangalore Central PHC", "type": "PHC", "district_code": districts[0]},
        {"name": "Koramangala CHC", "type": "CHC", "district_code": districts[0]},
        {"name": "Indiranagar PHC", "type": "PHC", "district_code": districts[0]},
        {"name": "Andheri East CHC", "type": "CHC", "district_code": districts[1]},
        {"name": "Bandra West PHC", "type": "PHC", "district_code": districts[1]},
    ]
    
    medicines = [
        ("Paracetamol 500mg", 10.5, 7, 100.0),
        ("Amoxicillin 250mg", 5.2, 5, 50.0),
        ("ORS Sachets", 20.0, 3, 200.0),
        ("Ibuprofen 400mg", 8.0, 10, 120.0),
        ("Cough Syrup 100ml", 15.0, 7, 150.0)
    ]
    
    roles = ["Receptionist", "PHC In-charge", "Doctor", "Nurse"]
    
    facilities = []
    for data in facilities_data:
        facility = Facility(
            district_code=data["district_code"],
            name=data["name"],
            type=data["type"],
            lat=float(fake.latitude()),
            lng=float(fake.longitude()),
            sanctioned_beds=random.randint(20, 100),
            available_beds=random.randint(5, 20),
            sanctioned_staff=random.randint(10, 50)
        )
        session.add(facility)
        facilities.append(facility)
    
    session.commit()
    print(f"Created {len(facilities)} facilities.")
    
    # Staff for each facility
    staff_members = []
    for facility in facilities:
        for _ in range(random.randint(5, 10)):
            staff = Staff(
                facility_id=facility.id,
                role=random.choice(roles),
                name=fake.name()
            )
            session.add(staff)
            staff_members.append(staff)
    
    session.commit()
    print(f"Created {len(staff_members)} staff members.")
    
    # Inventory items for each facility
    for facility in facilities:
        for med in medicines:
            # Add some randomness to current stock
            current_stock = int(med[3] + random.randint(-20, 50))
            if current_stock < 0:
                current_stock = 0
                
            item = InventoryItem(
                facility_id=facility.id,
                medicine_name=med[0],
                avg_daily_burn_rate=med[1],
                supply_lead_time=med[2],
                drp_value=med[3],
                current_stock=current_stock
            )
            session.add(item)
    
    session.commit()
    print("Created inventory items.")
    
    # A week of footfall logs for each facility
    today = datetime.now().date()
    for facility in facilities:
        for i in range(7):
            log_date = today - timedelta(days=i)
            log = FootfallLog(
                facility_id=facility.id,
                date=log_date,
                count=random.randint(50, 200)
            )
            session.add(log)
            
    session.commit()
    print("Created footfall logs for the last 7 days.")
    
    print("Database seeding completed successfully.")

if __name__ == '__main__':
    run_seed()
