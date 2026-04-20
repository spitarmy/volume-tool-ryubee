from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session
from app.database import get_db
from app import models, auth
from datetime import date

router = APIRouter(prefix="/v1/manifests", tags=["manifests"])


class ManifestCreate(BaseModel):
    job_id: str | None = None
    customer_id: str
    waste_type: str = ""
    issue_date: str | None = None
    expected_return_date: str | None = None
    actual_return_date: str | None = None
    status: str = "issued"
    manifest_number: str = ""
    weight_kg: float | None = None
    unit_price_per_kg: float = 30.0
    waste_category: str = "industrial"  # industrial / general


class ManifestUpdate(BaseModel):
    waste_type: str | None = None
    issue_date: str | None = None
    expected_return_date: str | None = None
    actual_return_date: str | None = None
    status: str | None = None
    manifest_number: str | None = None
    weight_kg: float | None = None
    unit_price_per_kg: float | None = None
    waste_category: str | None = None


class ManifestOut(BaseModel):
    id: str
    job_id: str | None
    customer_id: str
    customer_name: str = ""
    waste_type: str
    issue_date: str | None
    expected_return_date: str | None
    actual_return_date: str | None
    status: str
    manifest_number: str
    weight_kg: float | None
    unit_price_per_kg: float
    waste_category: str
    billing_amount: int = 0  # weight_kg × unit_price_per_kg
    created_at: str

    model_config = {"from_attributes": True}

    @classmethod
    def from_orm_obj(cls, obj: models.Manifest, customer_name: str = ""):
        amt = int((obj.weight_kg or 0) * (obj.unit_price_per_kg or 0))
        return cls(
            id=obj.id,
            job_id=obj.job_id,
            customer_id=obj.customer_id,
            customer_name=customer_name,
            waste_type=obj.waste_type,
            issue_date=obj.issue_date,
            expected_return_date=obj.expected_return_date,
            actual_return_date=obj.actual_return_date,
            status=obj.status,
            manifest_number=obj.manifest_number,
            weight_kg=obj.weight_kg,
            unit_price_per_kg=obj.unit_price_per_kg,
            waste_category=obj.waste_category,
            billing_amount=amt,
            created_at=obj.created_at.isoformat()
        )


@router.get("", response_model=list[ManifestOut])
def list_manifests(
    waste_category: str | None = Query(None, description="industrial/general"),
    status: str | None = Query(None),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    customers = db.query(models.Customer).filter_by(company_id=current_user.company_id).all()
    c_map = {c.id: c.name for c in customers}
    c_ids = list(c_map.keys())
    if not c_ids:
        return []
    q = db.query(models.Manifest).filter(models.Manifest.customer_id.in_(c_ids))
    if waste_category:
        q = q.filter(models.Manifest.waste_category == waste_category)
    if status:
        q = q.filter(models.Manifest.status == status)
    manifests = q.order_by(models.Manifest.created_at.desc()).all()
    return [ManifestOut.from_orm_obj(m, c_map.get(m.customer_id, "")) for m in manifests]


@router.get("/overdue", response_model=list[ManifestOut])
def overdue_manifests(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    """期限超過マニフェスト"""
    customers = db.query(models.Customer).filter_by(company_id=current_user.company_id).all()
    c_map = {c.id: c.name for c in customers}
    c_ids = list(c_map.keys())
    if not c_ids:
        return []
    today_str = date.today().isoformat()
    manifests = db.query(models.Manifest).filter(
        models.Manifest.customer_id.in_(c_ids),
        models.Manifest.status == "issued",
        models.Manifest.expected_return_date <= today_str,
        models.Manifest.actual_return_date.is_(None),
    ).order_by(models.Manifest.expected_return_date.asc()).all()
    return [ManifestOut.from_orm_obj(m, c_map.get(m.customer_id, "")) for m in manifests]


@router.post("", response_model=ManifestOut)
def create_manifest(
    body: ManifestCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    cust = db.query(models.Customer).filter_by(
        id=body.customer_id, company_id=current_user.company_id
    ).first()
    if not cust:
        raise HTTPException(404, "Customer not found")
    new_m = models.Manifest(**body.model_dump())
    db.add(new_m)
    db.commit()
    db.refresh(new_m)
    return ManifestOut.from_orm_obj(new_m, cust.name)


@router.put("/{manifest_id}", response_model=ManifestOut)
def update_manifest(
    manifest_id: str,
    body: ManifestUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    customers = db.query(models.Customer).filter_by(company_id=current_user.company_id).all()
    c_ids = [c.id for c in customers]
    c_map = {c.id: c.name for c in customers}
    m = db.query(models.Manifest).filter(
        models.Manifest.id == manifest_id,
        models.Manifest.customer_id.in_(c_ids),
    ).first()
    if not m:
        raise HTTPException(404, "マニフェストが見つかりません")
    for field, val in body.model_dump(exclude_none=True).items():
        setattr(m, field, val)
    db.commit()
    db.refresh(m)
    return ManifestOut.from_orm_obj(m, c_map.get(m.customer_id, ""))
