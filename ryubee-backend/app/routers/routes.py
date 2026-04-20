from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from app.database import get_db
from app import models, auth

router = APIRouter(prefix="/v1/routes", tags=["routes"])

class RouteCreate(BaseModel):
    date: str
    driver_id: str | None = None
    vehicle_name: str = ""
    status: str = "draft"

class RouteOut(BaseModel):
    id: str
    company_id: str
    driver_id: str | None
    date: str
    vehicle_name: str
    status: str
    created_at: str

    model_config = {"from_attributes": True}

    @classmethod
    def from_orm_obj(cls, obj: models.Route):
        return cls(
            id=obj.id,
            company_id=obj.company_id,
            driver_id=obj.driver_id,
            date=obj.date,
            vehicle_name=obj.vehicle_name,
            status=obj.status,
            created_at=obj.created_at.isoformat()
        )

@router.get("", response_model=list[RouteOut])
def list_routes(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    routes = db.query(models.Route).filter_by(company_id=current_user.company_id).all()
    return [RouteOut.from_orm_obj(r) for r in routes]

@router.post("", response_model=RouteOut)
def create_route(
    body: RouteCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    new_r = models.Route(
        company_id=current_user.company_id,
        date=body.date,
        driver_id=body.driver_id,
        vehicle_name=body.vehicle_name,
        status=body.status
    )
    db.add(new_r)
    db.commit()
    db.refresh(new_r)
    return RouteOut.from_orm_obj(new_r)
