from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session
from app.database import get_db
from app import models, auth

router = APIRouter(prefix="/v1/customers", tags=["customers"])


class CustomerCreate(BaseModel):
    name: str
    address: str = ""
    phone: str = ""
    contract_type: str = "spot"
    email: str = ""
    contact_person: str = ""
    notes: str = ""
    contract_expiry_date: str | None = None
    billing_closing_day: int = 31
    payment_due_month_offset: int = 1
    payment_due_day: int = 31
    bank_code: str = ""
    branch_code: str = ""
    account_type: str = "1"
    account_number: str = ""
    account_holder: str = ""
    form_data: str = "{}"
    assigned_user_id: str | None = None


class CustomerHistoryCreate(BaseModel):
    event_type: str = "note"
    description: str


class CustomerHistoryOut(BaseModel):
    id: str
    customer_id: str
    event_type: str
    description: str
    created_at: str

    model_config = {"from_attributes": True}

    @classmethod
    def from_orm_obj(cls, obj: models.CustomerHistory):
        return cls(
            id=str(obj.id),
            customer_id=str(obj.customer_id),
            event_type=str(obj.event_type),
            description=str(obj.description),
            created_at=obj.created_at.isoformat() if obj.created_at else ""
        )


class CustomerUpdate(BaseModel):
    name: str | None = None
    address: str | None = None
    phone: str | None = None
    contract_type: str | None = None
    email: str | None = None
    contact_person: str | None = None
    notes: str | None = None
    contract_expiry_date: str | None = None
    billing_closing_day: int | None = None
    payment_due_month_offset: int | None = None
    payment_due_day: int | None = None
    bank_code: str | None = None
    branch_code: str | None = None
    account_type: str | None = None
    account_number: str | None = None
    account_holder: str | None = None
    form_data: str | None = None
    assigned_user_id: str | None = None


class CustomerOut(BaseModel):
    id: str
    company_id: str
    name: str
    address: str
    phone: str
    contract_type: str
    email: str
    contact_person: str
    notes: str
    contract_expiry_date: str | None
    billing_closing_day: int = 31
    payment_due_month_offset: int = 1
    payment_due_day: int = 31
    bank_code: str = ""
    branch_code: str = ""
    account_type: str = "1"
    account_number: str = ""
    account_holder: str = ""
    form_data: str = "{}"
    assigned_user_id: str | None = None
    assigned_user_name: str | None = None
    created_at: str

    model_config = {"from_attributes": True}

    @classmethod
    def from_orm_obj(cls, obj: models.Customer):
        return cls(
            id=str(obj.id) if obj.id else "",
            company_id=str(obj.company_id) if obj.company_id else "",
            name=str(obj.name) if obj.name else "名称未設定",
            address=str(obj.address) if obj.address else "",
            phone=str(obj.phone) if obj.phone else "",
            contract_type=str(obj.contract_type) if obj.contract_type else "spot",
            email=str(obj.email) if obj.email else "",
            contact_person=str(obj.contact_person) if obj.contact_person else "",
            notes=str(obj.notes) if obj.notes else "",
            contract_expiry_date=str(obj.contract_expiry_date) if obj.contract_expiry_date else None,
            billing_closing_day=int(obj.billing_closing_day) if obj.billing_closing_day is not None else 31,
            payment_due_month_offset=int(obj.payment_due_month_offset) if obj.payment_due_month_offset is not None else 1,
            payment_due_day=int(obj.payment_due_day) if obj.payment_due_day is not None else 31,
            bank_code=str(getattr(obj, 'bank_code', '') or ''),
            branch_code=str(getattr(obj, 'branch_code', '') or ''),
            account_type=str(getattr(obj, 'account_type', '1') or '1'),
            account_number=str(getattr(obj, 'account_number', '') or ''),
            account_holder=str(getattr(obj, 'account_holder', '') or ''),
            form_data=str(obj.form_data) if obj.form_data else "{}",
            assigned_user_id=str(obj.assigned_user_id) if getattr(obj, 'assigned_user_id', None) else None,
            assigned_user_name=str(obj.assignee.name) if getattr(obj, 'assignee', None) else None,
            created_at=obj.created_at.isoformat() if obj.created_at else ""
        )


@router.get("")
def list_customers(
    search: str | None = Query(None, description="名前で検索"),
    assigned_user_id: str | None = Query(None, description="担当者IDで検索"),
    limit: int = Query(500, ge=1, le=2000),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    try:
        q = db.query(models.Customer).filter_by(
            company_id=current_user.company_id
        )
        if search:
            q = q.filter(models.Customer.name.ilike(f"%{search}%"))
        
        if assigned_user_id:
            q = q.filter(models.Customer.assigned_user_id == assigned_user_id)
            
        total = q.count()
        customers = q.order_by(models.Customer.created_at.desc()).offset(offset).limit(limit).all()
        return {
            "items": [CustomerOut.from_orm_obj(c).model_dump() for c in customers],
            "total": total,
            "limit": limit,
            "offset": offset,
        }
    except Exception as e:
        import traceback
        error_info = traceback.format_exc()
        raise HTTPException(status_code=400, detail=f"DEBUG ERROR: {str(e)}\n\n{error_info}")


@router.post("", response_model=CustomerOut)
def create_customer(
    body: CustomerCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    new_cust = models.Customer(
        company_id=current_user.company_id,
        name=body.name,
        address=body.address,
        phone=body.phone,
        contract_type=body.contract_type,
        email=body.email,
        contact_person=body.contact_person,
        notes=body.notes,
        contract_expiry_date=body.contract_expiry_date,
        billing_closing_day=body.billing_closing_day,
        payment_due_month_offset=body.payment_due_month_offset,
        payment_due_day=body.payment_due_day,
        form_data=body.form_data,
        assigned_user_id=body.assigned_user_id,
    )
    db.add(new_cust)
    db.commit()
    db.refresh(new_cust)
    return CustomerOut.from_orm_obj(new_cust)


@router.put("/{customer_id}", response_model=CustomerOut)
def update_customer(
    customer_id: str,
    body: CustomerUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    cust = db.query(models.Customer).filter_by(
        id=customer_id, company_id=current_user.company_id
    ).first()
    if not cust:
        raise HTTPException(404, "顧客が見つかりません")
    for field, val in body.model_dump(exclude_none=True).items():
        setattr(cust, field, val)
    db.commit()
    db.refresh(cust)
    return CustomerOut.from_orm_obj(cust)


@router.delete("/{customer_id}", status_code=204)
def delete_customer(
    customer_id: str,
    current_user: models.User = Depends(auth.require_admin),
    db: Session = Depends(get_db),
):
    cust = db.query(models.Customer).filter_by(
        id=customer_id, company_id=current_user.company_id
    ).first()
    if not cust:
        raise HTTPException(404, "顧客が見つかりません")
    db.delete(cust)
    db.commit()


@router.get("/{customer_id}/history")
def list_customer_history(
    customer_id: str,
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
):
    cust = db.query(models.Customer).filter_by(
        id=customer_id, company_id=current_user.company_id
    ).first()
    if not cust:
        raise HTTPException(404, "顧客が見つかりません")
    
    return [CustomerHistoryOut.from_orm_obj(h).model_dump() for h in cust.history_logs]


@router.post("/{customer_id}/history", response_model=CustomerHistoryOut)
def add_customer_history(
    customer_id: str,
    body: CustomerHistoryCreate,
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
):
    cust = db.query(models.Customer).filter_by(
        id=customer_id, company_id=current_user.company_id
    ).first()
    if not cust:
        raise HTTPException(404, "顧客が見つかりません")
    
    new_log = models.CustomerHistory(
        customer_id=customer_id,
        event_type=body.event_type,
        description=body.description
    )
    db.add(new_log)
    db.commit()
    db.refresh(new_log)
    return CustomerHistoryOut.from_orm_obj(new_log)
