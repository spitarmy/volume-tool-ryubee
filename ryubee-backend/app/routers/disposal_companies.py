import os
import uuid
import shutil
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import List, Optional

from app.database import get_db
from app.auth import get_current_user
from app.models import User, DisposalCompanyMaster

router = APIRouter(prefix="/v1/disposal-companies", tags=["Disposal Companies"])

UPLOADS_DIR = "uploads/permits"
os.makedirs(UPLOADS_DIR, exist_ok=True)

class DisposalCompanyCreate(BaseModel):
    name: str
    representative: str = ""
    address: str = ""
    permit_prefecture: str = "京都府"
    permit_number: str = ""
    facility_name: str = ""
    facility_address: str = ""
    permit_validity: str = "許可証に記載の通り"
    permit_category: str = "許可証に記載の通り"
    waste_types: str = "許可証に記載の通り"
    permit_conditions: str = "許可証に記載の通り"

class DisposalCompanyResponse(DisposalCompanyCreate):
    id: str
    permit_image_url: Optional[str] = None

    class Config:
        from_attributes = True

@router.get("/", response_model=List[DisposalCompanyResponse])
def get_all_disposal_companies(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    companies = db.query(DisposalCompanyMaster).filter(
        DisposalCompanyMaster.company_id == current_user.company_id
    ).order_by(DisposalCompanyMaster.created_at.desc()).all()
    return companies

@router.post("/", response_model=DisposalCompanyResponse)
def create_disposal_company(
    data: DisposalCompanyCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    new_company = DisposalCompanyMaster(
        company_id=current_user.company_id,
        **data.model_dump()
    )
    db.add(new_company)
    db.commit()
    db.refresh(new_company)
    return new_company

@router.put("/{company_id}", response_model=DisposalCompanyResponse)
def update_disposal_company(
    company_id: str,
    data: DisposalCompanyCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    company = db.query(DisposalCompanyMaster).filter(
        DisposalCompanyMaster.id == company_id,
        DisposalCompanyMaster.company_id == current_user.company_id
    ).first()
    if not company:
        raise HTTPException(status_code=404, detail="Disposal company not found")
    
    for key, value in data.model_dump().items():
        setattr(company, key, value)
        
    db.commit()
    db.refresh(company)
    return company

@router.delete("/{company_id}")
def delete_disposal_company(
    company_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    company = db.query(DisposalCompanyMaster).filter(
        DisposalCompanyMaster.id == company_id,
        DisposalCompanyMaster.company_id == current_user.company_id
    ).first()
    if not company:
        raise HTTPException(status_code=404, detail="Disposal company not found")
    
    db.delete(company)
    db.commit()
    return {"message": "Deleted successfully"}

@router.post("/{company_id}/upload-permit")
def upload_permit_image(
    company_id: str,
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    company = db.query(DisposalCompanyMaster).filter(
        DisposalCompanyMaster.id == company_id,
        DisposalCompanyMaster.company_id == current_user.company_id
    ).first()
    if not company:
        raise HTTPException(status_code=404, detail="Disposal company not found")

    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in [".jpg", ".jpeg", ".png", ".pdf"]:
        raise HTTPException(status_code=400, detail="Only JPG/PNG/PDF files are allowed")

    filename = f"permit_{company_id}_{uuid.uuid4().hex[:8]}{ext}"
    filepath = os.path.join(UPLOADS_DIR, filename)

    try:
        with open(filepath, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
    except Exception as e:
        raise HTTPException(status_code=500, detail="File upload failed")

    file_url = f"/uploads/permits/{filename}"
    company.permit_image_url = file_url
    db.commit()
    db.refresh(company)

    return {"message": "Permit uploaded", "url": file_url}
