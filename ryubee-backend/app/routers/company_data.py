"""
社内データ管理ルーター — 車両・許可証・3社契約 CRUD + アラート + 車両履歴 + 研修資料
"""
import os
import shutil
from datetime import datetime, date, timedelta
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from pydantic import BaseModel
from sqlalchemy.orm import Session
from app.database import get_db
from app.auth import get_current_user
from app.models import Vehicle, Permit, WasteContract, VehicleRecord, TrainingMaterial

UPLOAD_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "uploads")
os.makedirs(os.path.join(UPLOAD_DIR, "vehicle_records"), exist_ok=True)
os.makedirs(os.path.join(UPLOAD_DIR, "training"), exist_ok=True)

router = APIRouter(prefix="/v1", tags=["company-data"])


# ── Pydantic Schemas ─────────────────────────────────────

class VehicleIn(BaseModel):
    plate_area: str = ""
    plate_class: str = ""
    plate_kana: str = ""
    plate_number: str = ""
    vehicle_number: str = ""
    maker: str = ""
    code: str = ""
    vehicle_type: str = ""
    max_capacity_kg: int | None = None
    driver_name: str = ""
    first_registration: str | None = None
    inspection_expiry: str | None = None
    tire_replacement_date: str | None = None
    notes: str = ""


class PermitIn(BaseModel):
    prefecture: str = ""
    permit_type: str = ""
    permit_number: str = ""
    expiry_date: str | None = None
    application_month: str = ""
    notes: str = ""


class WasteContractIn(BaseModel):
    contract_name: str = ""
    contractor_name: str = ""
    disposal_company: str = ""
    transport_company: str = ""
    waste_type: str = ""
    contract_date: str | None = None
    expiry_date: str | None = None
    document_url: str = ""
    notes: str = ""


# ── helpers ──────────────────────────────────────────────

def _to_dict(obj, fields):
    return {f: getattr(obj, f) for f in fields}


VEHICLE_FIELDS = [
    "id", "plate_area", "plate_class", "plate_kana", "plate_number",
    "vehicle_number", "maker", "code", "vehicle_type", "max_capacity_kg",
    "driver_name", "first_registration", "inspection_expiry",
    "tire_replacement_date", "notes",
]

PERMIT_FIELDS = [
    "id", "prefecture", "permit_type", "permit_number",
    "expiry_date", "application_month", "notes",
]

CONTRACT_FIELDS = [
    "id", "contract_name", "contractor_name", "disposal_company",
    "transport_company", "waste_type", "contract_date",
    "expiry_date", "document_url", "notes",
]


def _vehicle_dict(v):
    d = _to_dict(v, VEHICLE_FIELDS)
    d["created_at"] = v.created_at.isoformat() if v.created_at else None
    return d


def _permit_dict(p):
    d = _to_dict(p, PERMIT_FIELDS)
    d["created_at"] = p.created_at.isoformat() if p.created_at else None
    return d


def _contract_dict(c):
    d = _to_dict(c, CONTRACT_FIELDS)
    d["created_at"] = c.created_at.isoformat() if c.created_at else None
    return d


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  VEHICLES
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@router.get("/vehicles")
def list_vehicles(user=Depends(get_current_user), db: Session = Depends(get_db)):
    rows = db.query(Vehicle).filter(Vehicle.company_id == user["company_id"]).order_by(Vehicle.vehicle_number).all()
    return [_vehicle_dict(r) for r in rows]


@router.post("/vehicles", status_code=201)
def create_vehicle(body: VehicleIn, user=Depends(get_current_user), db: Session = Depends(get_db)):
    v = Vehicle(company_id=user["company_id"], **body.model_dump())
    db.add(v)
    db.commit()
    db.refresh(v)
    return _vehicle_dict(v)


@router.put("/vehicles/{vid}")
def update_vehicle(vid: str, body: VehicleIn, user=Depends(get_current_user), db: Session = Depends(get_db)):
    v = db.query(Vehicle).filter(Vehicle.id == vid, Vehicle.company_id == user["company_id"]).first()
    if not v:
        raise HTTPException(404, "Vehicle not found")
    for k, val in body.model_dump().items():
        setattr(v, k, val)
    db.commit()
    db.refresh(v)
    return _vehicle_dict(v)


@router.delete("/vehicles/{vid}", status_code=204)
def delete_vehicle(vid: str, user=Depends(get_current_user), db: Session = Depends(get_db)):
    v = db.query(Vehicle).filter(Vehicle.id == vid, Vehicle.company_id == user["company_id"]).first()
    if not v:
        raise HTTPException(404, "Vehicle not found")
    db.delete(v)
    db.commit()


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  PERMITS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@router.get("/permits")
def list_permits(user=Depends(get_current_user), db: Session = Depends(get_db)):
    rows = db.query(Permit).filter(Permit.company_id == user["company_id"]).order_by(Permit.prefecture).all()
    return [_permit_dict(r) for r in rows]


@router.post("/permits", status_code=201)
def create_permit(body: PermitIn, user=Depends(get_current_user), db: Session = Depends(get_db)):
    p = Permit(company_id=user["company_id"], **body.model_dump())
    db.add(p)
    db.commit()
    db.refresh(p)
    return _permit_dict(p)


@router.put("/permits/{pid}")
def update_permit(pid: str, body: PermitIn, user=Depends(get_current_user), db: Session = Depends(get_db)):
    p = db.query(Permit).filter(Permit.id == pid, Permit.company_id == user["company_id"]).first()
    if not p:
        raise HTTPException(404, "Permit not found")
    for k, val in body.model_dump().items():
        setattr(p, k, val)
    db.commit()
    db.refresh(p)
    return _permit_dict(p)


@router.delete("/permits/{pid}", status_code=204)
def delete_permit(pid: str, user=Depends(get_current_user), db: Session = Depends(get_db)):
    p = db.query(Permit).filter(Permit.id == pid, Permit.company_id == user["company_id"]).first()
    if not p:
        raise HTTPException(404, "Permit not found")
    db.delete(p)
    db.commit()


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  WASTE CONTRACTS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@router.get("/waste-contracts")
def list_waste_contracts(user=Depends(get_current_user), db: Session = Depends(get_db)):
    rows = db.query(WasteContract).filter(WasteContract.company_id == user["company_id"]).order_by(WasteContract.contract_name).all()
    return [_contract_dict(r) for r in rows]


@router.post("/waste-contracts", status_code=201)
def create_waste_contract(body: WasteContractIn, user=Depends(get_current_user), db: Session = Depends(get_db)):
    c = WasteContract(company_id=user["company_id"], **body.model_dump())
    db.add(c)
    db.commit()
    db.refresh(c)
    return _contract_dict(c)


@router.put("/waste-contracts/{cid}")
def update_waste_contract(cid: str, body: WasteContractIn, user=Depends(get_current_user), db: Session = Depends(get_db)):
    c = db.query(WasteContract).filter(WasteContract.id == cid, WasteContract.company_id == user["company_id"]).first()
    if not c:
        raise HTTPException(404, "Contract not found")
    for k, val in body.model_dump().items():
        setattr(c, k, val)
    db.commit()
    db.refresh(c)
    return _contract_dict(c)


@router.delete("/waste-contracts/{cid}", status_code=204)
def delete_waste_contract(cid: str, user=Depends(get_current_user), db: Session = Depends(get_db)):
    c = db.query(WasteContract).filter(WasteContract.id == cid, WasteContract.company_id == user["company_id"]).first()
    if not c:
        raise HTTPException(404, "Contract not found")
    db.delete(c)
    db.commit()


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  ALERTS — 更新期限アラート
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def _parse_date(s: str | None):
    """YYYY-MM-DD 形式の日付文字列をパース"""
    if not s:
        return None
    try:
        return date.fromisoformat(s)
    except (ValueError, TypeError):
        return None


@router.get("/company-data/alerts")
def get_data_alerts(user=Depends(get_current_user), db: Session = Depends(get_db)):
    """車検・許可・契約の期限切れ/期限間近を一括返却"""
    today = date.today()
    warn_30 = today + timedelta(days=30)
    warn_60 = today + timedelta(days=60)
    alerts = []

    # 車検満了日
    vehicles = db.query(Vehicle).filter(Vehicle.company_id == user["company_id"]).all()
    for v in vehicles:
        d = _parse_date(v.inspection_expiry)
        if d is None:
            continue
        if d < today:
            alerts.append({"type": "vehicle", "level": "expired", "label": f"🚛 {v.plate_area} {v.plate_class} {v.plate_kana} {v.plate_number}", "detail": f"車検期限切れ ({v.inspection_expiry})", "date": v.inspection_expiry, "id": v.id})
        elif d <= warn_30:
            alerts.append({"type": "vehicle", "level": "urgent", "label": f"🚛 {v.plate_area} {v.plate_class} {v.plate_kana} {v.plate_number}", "detail": f"車検 30日以内 ({v.inspection_expiry})", "date": v.inspection_expiry, "id": v.id})
        elif d <= warn_60:
            alerts.append({"type": "vehicle", "level": "warning", "label": f"🚛 {v.plate_area} {v.plate_class} {v.plate_kana} {v.plate_number}", "detail": f"車検 60日以内 ({v.inspection_expiry})", "date": v.inspection_expiry, "id": v.id})

    # 許可証
    permits = db.query(Permit).filter(Permit.company_id == user["company_id"]).all()
    for p in permits:
        d = _parse_date(p.expiry_date)
        if d is None:
            continue
        if d < today:
            alerts.append({"type": "permit", "level": "expired", "label": f"📋 {p.prefecture} {p.permit_type}", "detail": f"許可期限切れ ({p.expiry_date})", "date": p.expiry_date, "id": p.id})
        elif d <= warn_30:
            alerts.append({"type": "permit", "level": "urgent", "label": f"📋 {p.prefecture} {p.permit_type}", "detail": f"許可 30日以内 ({p.expiry_date})", "date": p.expiry_date, "id": p.id})
        elif d <= warn_60:
            alerts.append({"type": "permit", "level": "warning", "label": f"📋 {p.prefecture} {p.permit_type}", "detail": f"許可 60日以内 ({p.expiry_date})", "date": p.expiry_date, "id": p.id})

    # 3社契約
    contracts = db.query(WasteContract).filter(WasteContract.company_id == user["company_id"]).all()
    for c in contracts:
        d = _parse_date(c.expiry_date)
        if d is None:
            continue
        if d < today:
            alerts.append({"type": "contract", "level": "expired", "label": f"📄 {c.contract_name}", "detail": f"契約期限切れ ({c.expiry_date})", "date": c.expiry_date, "id": c.id})
        elif d <= warn_30:
            alerts.append({"type": "contract", "level": "urgent", "label": f"📄 {c.contract_name}", "detail": f"契約 30日以内 ({c.expiry_date})", "date": c.expiry_date, "id": c.id})
        elif d <= warn_60:
            alerts.append({"type": "contract", "level": "warning", "label": f"📄 {c.contract_name}", "detail": f"契約 60日以内 ({c.expiry_date})", "date": c.expiry_date, "id": c.id})

    # 緊急度でソート (expired > urgent > warning)
    level_order = {"expired": 0, "urgent": 1, "warning": 2}
    alerts.sort(key=lambda a: level_order.get(a["level"], 9))
    return alerts


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  VEHICLE RECORDS — 修理歴・事故歴・車検証
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

VEHICLE_RECORD_FIELDS = [
    "id", "vehicle_id", "record_type", "record_date",
    "title", "description", "file_url", "cost",
]


def _record_dict(r):
    d = {f: getattr(r, f) for f in VEHICLE_RECORD_FIELDS}
    d["created_at"] = r.created_at.isoformat() if r.created_at else None
    return d


@router.get("/vehicles/{vid}/records")
def list_vehicle_records(vid: str, user=Depends(get_current_user), db: Session = Depends(get_db)):
    v = db.query(Vehicle).filter(Vehicle.id == vid, Vehicle.company_id == user["company_id"]).first()
    if not v:
        raise HTTPException(404, "Vehicle not found")
    rows = db.query(VehicleRecord).filter(VehicleRecord.vehicle_id == vid).order_by(VehicleRecord.record_date.desc()).all()
    return [_record_dict(r) for r in rows]


@router.post("/vehicles/{vid}/records", status_code=201)
async def create_vehicle_record(
    vid: str,
    record_type: str = Form("repair"),
    record_date: str = Form(""),
    title: str = Form(""),
    description: str = Form(""),
    cost: int = Form(0),
    file: UploadFile | None = File(None),
    user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    v = db.query(Vehicle).filter(Vehicle.id == vid, Vehicle.company_id == user["company_id"]).first()
    if not v:
        raise HTTPException(404, "Vehicle not found")

    file_url = ""
    if file and file.filename:
        import uuid
        ext = os.path.splitext(file.filename)[1]
        fname = f"{uuid.uuid4().hex}{ext}"
        fpath = os.path.join(UPLOAD_DIR, "vehicle_records", fname)
        with open(fpath, "wb") as f:
            shutil.copyfileobj(file.file, f)
        file_url = f"/uploads/vehicle_records/{fname}"

    rec = VehicleRecord(
        vehicle_id=vid,
        record_type=record_type,
        record_date=record_date or None,
        title=title,
        description=description,
        file_url=file_url,
        cost=cost or None,
    )
    db.add(rec)
    db.commit()
    db.refresh(rec)
    return _record_dict(rec)


@router.delete("/vehicles/{vid}/records/{rid}", status_code=204)
def delete_vehicle_record(vid: str, rid: str, user=Depends(get_current_user), db: Session = Depends(get_db)):
    v = db.query(Vehicle).filter(Vehicle.id == vid, Vehicle.company_id == user["company_id"]).first()
    if not v:
        raise HTTPException(404, "Vehicle not found")
    rec = db.query(VehicleRecord).filter(VehicleRecord.id == rid, VehicleRecord.vehicle_id == vid).first()
    if not rec:
        raise HTTPException(404, "Record not found")
    db.delete(rec)
    db.commit()


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  TRAINING MATERIALS — 研修資料
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def _training_dict(t):
    return {
        "id": t.id, "title": t.title, "file_url": t.file_url,
        "file_type": t.file_type, "notes": t.notes,
        "created_at": t.created_at.isoformat() if t.created_at else None,
    }


@router.get("/training-materials")
def list_training_materials(user=Depends(get_current_user), db: Session = Depends(get_db)):
    rows = db.query(TrainingMaterial).filter(
        TrainingMaterial.company_id == user["company_id"]
    ).order_by(TrainingMaterial.created_at.desc()).all()
    return [_training_dict(r) for r in rows]


@router.post("/training-materials", status_code=201)
async def create_training_material(
    title: str = Form(""),
    notes: str = Form(""),
    file: UploadFile = File(...),
    user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    import uuid
    ext = os.path.splitext(file.filename)[1].lower()
    file_type = "pdf" if ext == ".pdf" else "image"
    fname = f"{uuid.uuid4().hex}{ext}"
    fpath = os.path.join(UPLOAD_DIR, "training", fname)
    with open(fpath, "wb") as f:
        shutil.copyfileobj(file.file, f)
    file_url = f"/uploads/training/{fname}"

    mat = TrainingMaterial(
        company_id=user["company_id"],
        title=title or file.filename,
        file_url=file_url,
        file_type=file_type,
        notes=notes,
    )
    db.add(mat)
    db.commit()
    db.refresh(mat)
    return _training_dict(mat)


@router.delete("/training-materials/{mid}", status_code=204)
def delete_training_material(mid: str, user=Depends(get_current_user), db: Session = Depends(get_db)):
    m = db.query(TrainingMaterial).filter(
        TrainingMaterial.id == mid, TrainingMaterial.company_id == user["company_id"]
    ).first()
    if not m:
        raise HTTPException(404, "Material not found")
    db.delete(m)
    db.commit()
