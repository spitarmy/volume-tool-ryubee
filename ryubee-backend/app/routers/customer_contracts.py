"""
顧客別処分先契約ルーター — Customer-level disposal contract CRUD
産廃3社間契約の追跡管理（送付日・返却日・排受・マニ登録・完了日）
"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from app.database import get_db
from app.auth import get_current_user
from app.models import CustomerContract, User

router = APIRouter(prefix="/v1/customers", tags=["Customer Contracts"])


# ── Pydantic Schemas ─────────────────────────────────────

class CustomerContractIn(BaseModel):
    disposal_company: str = ""
    waste_type: str = ""
    unit_price: float | None = None
    unit: str = "kg"
    contract_date: str | None = None
    expiry_date: str | None = None
    delivery_method: str = ""
    sent_date: str | None = None
    returned_date: str | None = None
    accepted: bool = False
    manifest_registered: bool = False
    completion_date: str | None = None
    status: str = "pending"
    notes: str = ""


# ── helpers ──────────────────────────────────────────────

CUSTOMER_CONTRACT_FIELDS = [
    "id", "customer_id", "disposal_company", "waste_type",
    "unit_price", "unit", "contract_date", "expiry_date",
    "delivery_method", "sent_date", "returned_date",
    "accepted", "manifest_registered", "completion_date",
    "status", "notes",
]


def _contract_dict(c):
    d = {f: getattr(c, f, None) for f in CUSTOMER_CONTRACT_FIELDS}
    d["created_at"] = c.created_at.isoformat() if c.created_at else None
    d["updated_at"] = c.updated_at.isoformat() if c.updated_at else None
    return d


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  CUSTOMER CONTRACTS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@router.get("/{cid}/contracts")
def list_customer_contracts(cid: str, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    rows = db.query(CustomerContract).filter(
        CustomerContract.customer_id == cid,
        CustomerContract.company_id == current_user.company_id,
    ).order_by(CustomerContract.created_at.desc()).all()
    return [_contract_dict(r) for r in rows]


@router.post("/{cid}/contracts", status_code=201)
def create_customer_contract(cid: str, body: CustomerContractIn, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    c = CustomerContract(
        company_id=current_user.company_id,
        customer_id=cid,
        **body.model_dump(),
    )
    db.add(c)
    db.commit()
    db.refresh(c)
    return _contract_dict(c)


@router.put("/{cid}/contracts/{contract_id}")
def update_customer_contract(cid: str, contract_id: str, body: CustomerContractIn, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    c = db.query(CustomerContract).filter(
        CustomerContract.id == contract_id,
        CustomerContract.customer_id == cid,
        CustomerContract.company_id == current_user.company_id,
    ).first()
    if not c:
        raise HTTPException(404, "Contract not found")
    for k, val in body.model_dump().items():
        setattr(c, k, val)
    db.commit()
    db.refresh(c)
    return _contract_dict(c)


@router.delete("/{cid}/contracts/{contract_id}", status_code=204)
def delete_customer_contract(cid: str, contract_id: str, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    c = db.query(CustomerContract).filter(
        CustomerContract.id == contract_id,
        CustomerContract.customer_id == cid,
        CustomerContract.company_id == current_user.company_id,
    ).first()
    if not c:
        raise HTTPException(404, "Contract not found")
    db.delete(c)
    db.commit()
