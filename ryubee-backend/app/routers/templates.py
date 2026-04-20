from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from app.database import get_db
from app import models, auth

router = APIRouter(prefix="/v1/templates", tags=["templates"])

class ItemTemplateCreate(BaseModel):
    name: str
    unit_price: float = 0
    unit: str = "式"
    description: str = ""

class ItemTemplateUpdate(BaseModel):
    name: str | None = None
    unit_price: float | None = None
    unit: str | None = None
    description: str | None = None

class ItemTemplateOut(BaseModel):
    id: str
    company_id: str
    name: str
    unit_price: float
    unit: str
    description: str
    created_at: str

    model_config = {"from_attributes": True}

    @classmethod
    def from_orm_obj(cls, obj: models.ItemTemplate):
        return cls(
            id=obj.id,
            company_id=obj.company_id,
            name=obj.name,
            unit_price=obj.unit_price,
            unit=obj.unit,
            description=obj.description,
            created_at=obj.created_at.isoformat()
        )

@router.get("", response_model=list[ItemTemplateOut])
def list_templates(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    temps = db.query(models.ItemTemplate).filter_by(
        company_id=current_user.company_id
    ).order_by(models.ItemTemplate.created_at.desc()).all()
    return [ItemTemplateOut.from_orm_obj(t) for t in temps]

@router.post("", response_model=ItemTemplateOut, status_code=201)
def create_template(
    body: ItemTemplateCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    t = models.ItemTemplate(
        company_id=current_user.company_id,
        **body.model_dump()
    )
    db.add(t)
    db.commit()
    db.refresh(t)
    return ItemTemplateOut.from_orm_obj(t)

@router.put("/{template_id}", response_model=ItemTemplateOut)
def update_template(
    template_id: str,
    body: ItemTemplateUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    t = db.query(models.ItemTemplate).filter_by(
        id=template_id, company_id=current_user.company_id
    ).first()
    if not t:
        raise HTTPException(404, "テンプレートが見つかりません")
    
    for field, val in body.model_dump(exclude_unset=True).items():
        if val is not None:
            setattr(t, field, val)
            
    db.commit()
    db.refresh(t)
    return ItemTemplateOut.from_orm_obj(t)

@router.delete("/{template_id}", status_code=204)
def delete_template(
    template_id: str,
    current_user: models.User = Depends(auth.require_admin),
    db: Session = Depends(get_db),
):
    t = db.query(models.ItemTemplate).filter_by(
        id=template_id, company_id=current_user.company_id
    ).first()
    if not t:
        raise HTTPException(404, "テンプレートが見つかりません")
    
    db.delete(t)
    db.commit()
