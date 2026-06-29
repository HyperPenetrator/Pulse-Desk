import re
import uuid
from datetime import datetime
from typing import Optional, Any
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, status
from sqlalchemy.orm import Session
from comms_client import transcribe_audio
from database import get_db
from dependencies import RequireRole
from models import InventoryItem, FootfallLog, Staff, AttendanceLog

router = APIRouter(prefix="/api/v1/voice", tags=["voice"])

def parse_number(text: str) -> Optional[int]:
    """
    Helper to extract a digit from text.
    """
    match = re.search(r'\b\d+\b', text)
    if match:
        return int(match.group(0))
    return None

def process_intent_routing(db: Session, text: str, facility_id: uuid.UUID) -> tuple[str, Optional[str], Optional[Any]]:
    """
    Analyzes the transcribed text, routes to the appropriate entity update,
    and returns a tuple of (intent, extracted_entity, extracted_value).
    """
    text_lower = text.lower().strip()
    today = datetime.utcnow().date()
    
    # 1. Check for Attendance Log
    # Fetch all staff for this facility
    staff_members = db.query(Staff).filter(Staff.facility_id == facility_id).all()
    matched_staff = None
    for s in staff_members:
        # Check if staff name is in the text
        if s.name.lower() in text_lower:
            matched_staff = s
            break
            
    if matched_staff:
        # Check if keywords indicate attendance
        attendance_keywords = ["present", "absent", "leave", "arrived", "aaya", "haazir", "chutti", "chuti"]
        if any(kw in text_lower for kw in attendance_keywords):
            # Determine status
            status_str = "Present"
            if "absent" in text_lower:
                status_str = "Absent"
            elif "leave" in text_lower or "chutti" in text_lower or "chuti" in text_lower:
                status_str = "Leave"
            
            # Write/Update Attendance Log
            log = db.query(AttendanceLog).filter(
                AttendanceLog.staff_id == matched_staff.id,
                AttendanceLog.date == today
            ).first()
            if not log:
                log = AttendanceLog(
                    id=uuid.uuid4(),
                    staff_id=matched_staff.id,
                    date=today,
                    status=status_str
                )
                db.add(log)
            else:
                log.status = status_str
            db.commit()
            return "attendance_log", matched_staff.name, status_str

    # 2. Check for Stock Update
    # Fetch inventory items for this facility
    inventory_items = db.query(InventoryItem).filter(InventoryItem.facility_id == facility_id).all()
    matched_item = None
    for item in inventory_items:
        if item.medicine_name.lower() in text_lower:
            matched_item = item
            break
            
    if matched_item:
        # We need a number or out of stock keywords
        stock_val = None
        # Check out of stock keywords
        out_of_stock_keywords = ["khatam", "out of", "zero", "none", "nil", "khatam ho gaya", "finish"]
        if any(kw in text_lower for kw in out_of_stock_keywords):
            stock_val = 0
        else:
            stock_val = parse_number(text_lower)
            
        if stock_val is not None:
            # Update current stock
            matched_item.current_stock = stock_val
            db.commit()
            return "stock_update", matched_item.medicine_name, stock_val

    # 3. Check for Footfall Count
    footfall_keywords = ["footfall", "opd", "patient", "patients", "visitor", "visitors", "mariiz", "footfall_count"]
    if any(kw in text_lower for kw in footfall_keywords):
        count_val = parse_number(text_lower)
        if count_val is not None:
            log = db.query(FootfallLog).filter(
                FootfallLog.facility_id == facility_id,
                FootfallLog.date == today
            ).first()
            if not log:
                log = FootfallLog(
                    id=uuid.uuid4(),
                    facility_id=facility_id,
                    date=today,
                    count=count_val
                )
                db.add(log)
            else:
                log.count = count_val
            db.commit()
            return "footfall_count", "footfall", count_val

    return "unclassified", None, None

@router.post("/transcribe", dependencies=[Depends(RequireRole(["receptionist", "phc_incharge", "district_admin"]))])
async def transcribe(
    file: UploadFile = File(...),
    language_code: Optional[str] = Form(None),
    db: Session = Depends(get_db),
    claims: dict = Depends(RequireRole(["receptionist", "phc_incharge", "district_admin"]))
):
    # Validate file type
    filename = file.filename.lower()
    allowed_extensions = (".mp3", ".wav", ".ogg", ".m4a")
    if not filename.endswith(allowed_extensions):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Unsupported audio format. Supported formats: .mp3, .wav, .ogg, .m4a"
        )
        
    # Read audio content
    audio_content = await file.read()
    
    # Transcribe audio
    transcription_result = transcribe_audio(audio_content, language_code)
    
    # Intent routing
    facility_id_str = claims.get("facility_id")
    if not facility_id_str:
        # District admins might not have a facility_id scope. If so, they cannot perform facility updates directly via voice.
        intent, extracted_entity, extracted_value = "unclassified", None, None
    else:
        facility_id = uuid.UUID(facility_id_str)
        intent, extracted_entity, extracted_value = process_intent_routing(
            db,
            transcription_result["transcribed_text"],
            facility_id
        )
        
    return {
        "transcribed_text": transcription_result["transcribed_text"],
        "confidence_score": transcription_result["confidence_score"],
        "detected_language_code": transcription_result["detected_language_code"],
        "intent": intent,
        "extracted_entity": extracted_entity,
        "extracted_value": extracted_value
    }
