from fastapi import Depends, HTTPException, status
from sqlalchemy.orm import Session
from uuid import UUID
from database import get_db
from auth import verify_token
from models import Facility

def get_current_user(claims: dict = Depends(verify_token)) -> dict:
    return claims

class RequireRole:
    def __init__(self, allowed_roles: list[str]):
        self.allowed_roles = allowed_roles

    def __call__(self, claims: dict = Depends(get_current_user)) -> dict:
        role = claims.get("role")
        if role not in self.allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Permission denied: role '{role}' is not in allowed roles: {self.allowed_roles}"
            )
        return claims

def validate_facility_scope(
    facility_id: UUID,
    claims: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
) -> dict:
    role = claims.get("role")
    
    if role in ["receptionist", "phc_incharge"]:
        user_facility_id = claims.get("facility_id")
        if not user_facility_id or str(user_facility_id) != str(facility_id):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied: user is not scoped to this facility"
            )
            
    elif role == "district_admin":
        user_district_code = claims.get("district_code")
        facility = db.query(Facility).filter(Facility.id == facility_id).first()
        if not facility:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Facility not found"
            )
        if not user_district_code or facility.district_code != user_district_code:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied: facility is outside your district scope"
            )
    else:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied: invalid role for facility scope"
        )
        
    return claims

def validate_district_scope(
    district_code: str,
    claims: dict = Depends(get_current_user)
) -> dict:
    role = claims.get("role")
    
    if role == "district_admin":
        user_district_code = claims.get("district_code")
        if not user_district_code or user_district_code != district_code:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied: district is outside your admin scope"
            )
    elif role in ["receptionist", "phc_incharge"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied: receptionist/phc_incharge roles cannot access district-level endpoints"
        )
    else:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied: invalid role for district scope"
        )
        
    return claims
