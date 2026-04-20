import logging
from typing import List, Optional
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session
from sqlalchemy import func

from app import models, auth
from app.database import get_db

router = APIRouter(prefix="/daily_reports", tags=["Daily Reports"])

class DailyReportCreate(BaseModel):
    report_date: str
    customer_id: Optional[str] = None
    customer_name: Optional[str] = ""
    bag_count: int = 0
    weight_kg: float = 0.0
    notes: Optional[str] = ""

class DailyReportUpdate(BaseModel):
    report_date: Optional[str] = None
    customer_id: Optional[str] = None
    customer_name: Optional[str] = None
    bag_count: Optional[int] = None
    weight_kg: Optional[float] = None
    notes: Optional[str] = None

class DailyReportResponse(BaseModel):
    id: str
    driver_id: str
    driver_name: str
    customer_id: Optional[str]
    customer_name: str
    report_date: str
    bag_count: int
    weight_kg: float
    notes: str
    created_at: datetime
    
    model_config = ConfigDict(from_attributes=True)

@router.get("/", response_model=List[DailyReportResponse])
def get_daily_reports(
    month: Optional[str] = Query(None, description="YYYY-MM"),
    driver_id: Optional[str] = Query(None),
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db)
):
    query = db.query(models.DailyReport).filter_by(company_id=current_user.company_id)
    
    # ドライバーは自分のデータのみ、管理者は全員見れるようにすべきだが、簡単のため一旦そのまま取得
    if driver_id:
        query = query.filter(models.DailyReport.driver_id == driver_id)
        
    if month:
        query = query.filter(models.DailyReport.report_date.startswith(month))
        
    reports = query.order_by(models.DailyReport.report_date.desc(), models.DailyReport.created_at.desc()).all()
    
    ret = []
    for r in reports:
        driver = db.query(models.User).filter_by(id=r.driver_id).first()
        driver_name = driver.name if driver else "不明"
        
        # 顧客情報
        c_name = r.customer_name
        if r.customer_id:
            cust = db.query(models.Customer).filter_by(id=r.customer_id).first()
            if cust:
                c_name = cust.name

        ret.append({
            "id": r.id,
            "driver_id": r.driver_id,
            "driver_name": driver_name,
            "customer_id": r.customer_id,
            "customer_name": c_name,
            "report_date": r.report_date,
            "bag_count": r.bag_count,
            "weight_kg": r.weight_kg,
            "notes": r.notes,
            "created_at": r.created_at
        })
    return ret

@router.post("/", response_model=DailyReportResponse)
def create_daily_report(
    req: DailyReportCreate,
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db)
):
    report = models.DailyReport(
        company_id=current_user.company_id,
        driver_id=current_user.id,
        report_date=req.report_date,
        customer_id=req.customer_id,
        customer_name=req.customer_name or "",
        bag_count=req.bag_count,
        weight_kg=req.weight_kg,
        notes=req.notes or ""
    )
    db.add(report)
    db.commit()
    db.refresh(report)
    
    return {
        "id": report.id,
        "driver_id": report.driver_id,
        "driver_name": current_user.name,
        "customer_id": report.customer_id,
        "customer_name": report.customer_name,
        "report_date": report.report_date,
        "bag_count": report.bag_count,
        "weight_kg": report.weight_kg,
        "notes": report.notes,
        "created_at": report.created_at
    }

@router.delete("/{report_id}")
def delete_daily_report(
    report_id: str,
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db)
):
    report = db.query(models.DailyReport).filter_by(id=report_id, company_id=current_user.company_id).first()
    if not report:
        raise HTTPException(status_code=404, detail="Not found")
        
    db.delete(report)
    db.commit()
    return {"status": "ok"}
