"""案件ルーター: 案件CRUD（テナント分離あり）+ パイプライン + 写真"""
import json
from typing import Any
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session
from app.database import get_db
from app import models, auth

router = APIRouter(prefix="/v1/jobs", tags=["jobs"])


# ── Schemas ────────────────────────────────────────────
class JobCreate(BaseModel):
    job_name: str
    customer_name: str = ""
    address: str = ""
    work_date: str | None = None
    notes: str = ""
    total_volume_m3: float | None = None
    price_total: int = 0
    status: str = "pending"
    ai_result: Any = None
    pipeline_stage: str = "inquiry"
    job_type: str = "other"
    assigned_to: str | None = None
    customer_id: str | None = None
    form_data: str = "{}"


class JobUpdate(BaseModel):
    job_name: str | None = None
    customer_name: str | None = None
    customer_id: str | None = None
    address: str | None = None
    work_date: str | None = None
    notes: str | None = None
    total_volume_m3: float | None = None
    price_total: int | None = None
    status: str | None = None
    signature_data: str | None = None
    ai_result: Any | None = None
    pipeline_stage: str | None = None
    job_type: str | None = None
    assigned_to: str | None = None
    photos: str | None = None  # JSON array string
    form_data: str | None = None
    estimated_price: int | None = None
    final_price: int | None = None
    discount_amount: int | None = None
    surcharge_amount: int | None = None
    price_notes: str | None = None


class JobOut(BaseModel):
    job_id: str
    company_id: str
    user_id: str | None
    job_name: str
    customer_name: str
    address: str
    work_date: str | None
    notes: str
    total_volume_m3: float | None
    price_total: int
    status: str
    signature_data: str
    ai_result: Any
    pipeline_stage: str
    job_type: str
    assigned_to: str | None
    assigned_to_name: str = ""
    photos: Any  # JSON array
    estimated_price: int | None = None
    final_price: int | None = None
    discount_amount: int = 0
    surcharge_amount: int = 0
    price_notes: str = ""
    form_data: str = "{}"
    comment_count: int = 0
    created_at: str
    updated_at: str

    model_config = {"from_attributes": True}

    @classmethod
    def from_orm_job(cls, j: models.Job) -> "JobOut":
        ai = j.ai_result
        if ai:
            try:
                ai = json.loads(ai)
            except Exception:
                pass

        photos = []
        if j.photos:
            try:
                photos = json.loads(j.photos)
            except Exception:
                pass

        assignee_name = ""
        if j.assignee:
            assignee_name = j.assignee.name

        return cls(
            job_id=j.job_id,
            company_id=j.company_id,
            user_id=j.user_id,
            job_name=j.job_name,
            customer_name=j.customer_name,
            address=j.address,
            work_date=j.work_date,
            notes=j.notes,
            total_volume_m3=j.total_volume_m3,
            price_total=j.price_total,
            status=j.status,
            signature_data=j.signature_data,
            ai_result=ai,
            pipeline_stage=j.pipeline_stage,
            job_type=j.job_type,
            assigned_to=j.assigned_to,
            assigned_to_name=assignee_name,
            photos=photos,
            estimated_price=j.estimated_price,
            final_price=j.final_price,
            discount_amount=j.discount_amount,
            surcharge_amount=j.surcharge_amount,
            price_notes=j.price_notes,
            form_data=j.form_data or "{}",
            comment_count=len(j.comments) if j.comments else 0,
            created_at=j.created_at.isoformat(),
            updated_at=j.updated_at.isoformat(),
        )


# ── Endpoints ──────────────────────────────────────────
@router.get("", response_model=list[JobOut])
def list_jobs(
    status: str | None = Query(None, description="pending/confirmed/completed でフィルタ"),
    q: str | None = Query(None, description="案件名・顧客名の検索"),
    pipeline_stage: str | None = Query(None),
    job_type: str | None = Query(None),
    customer_id: str | None = Query(None),
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
):
    """自社案件一覧（テナント分離: company_id で絞り込み）"""
    query = db.query(models.Job).filter_by(company_id=current_user.company_id)
    if status:
        query = query.filter(models.Job.status == status)
    if pipeline_stage:
        query = query.filter(models.Job.pipeline_stage == pipeline_stage)
    if job_type:
        query = query.filter(models.Job.job_type == job_type)
    if customer_id:
        query = query.filter(models.Job.customer_id == customer_id)
    if q:
        like = f"%{q}%"
        query = query.filter(
            models.Job.job_name.ilike(like) | models.Job.customer_name.ilike(like)
        )
    jobs = query.order_by(models.Job.created_at.desc()).all()
    return [JobOut.from_orm_job(j) for j in jobs]


@router.get("/pipeline")
def pipeline_view(
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
):
    """営業パイプライン: カンバン形式でステージ別グルーピング"""
    stages = ["inquiry", "estimate", "negotiation", "contract", "scheduled", "waiting_manifest", "completed", "lost"]
    jobs = db.query(models.Job).filter_by(
        company_id=current_user.company_id
    ).order_by(models.Job.updated_at.desc()).all()

    pipeline = {}
    for stage in stages:
        pipeline[stage] = []
    for j in jobs:
        stage = j.pipeline_stage if j.pipeline_stage in stages else "inquiry"
        pipeline[stage].append(JobOut.from_orm_job(j).model_dump())

    return pipeline


@router.post("", response_model=JobOut, status_code=201)
def create_job(
    body: JobCreate,
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
):
    ai_str = json.dumps(body.ai_result, ensure_ascii=False) if body.ai_result else ""
    job = models.Job(
        company_id=current_user.company_id,
        user_id=current_user.id,
        job_name=body.job_name,
        customer_name=body.customer_name,
        address=body.address,
        work_date=body.work_date,
        notes=body.notes,
        total_volume_m3=body.total_volume_m3,
        price_total=body.price_total,
        status=body.status,
        ai_result=ai_str,
        pipeline_stage=body.pipeline_stage,
        job_type=body.job_type,
        assigned_to=body.assigned_to,
        customer_id=body.customer_id,
        form_data=body.form_data,
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    return JobOut.from_orm_job(job)


@router.get("/{job_id}", response_model=JobOut)
def get_job(
    job_id: str,
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
):
    job = _get_own_job(job_id, current_user, db)
    return JobOut.from_orm_job(job)


@router.put("/{job_id}", response_model=JobOut)
def update_job(
    job_id: str,
    body: JobUpdate,
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
):
    job = _get_own_job(job_id, current_user, db)

    for field, val in body.model_dump(exclude_none=True).items():
        if field == "ai_result" and val is not None:
            val = json.dumps(val, ensure_ascii=False)
        setattr(job, field, val)

    db.commit()
    db.refresh(job)
    return JobOut.from_orm_job(job)


@router.delete("/{job_id}", status_code=204)
def delete_job(
    job_id: str,
    current_user: models.User = Depends(auth.require_admin),
    db: Session = Depends(get_db),
):
    job = _get_own_job(job_id, current_user, db)
    db.delete(job)
    db.commit()


# ── Comments ───────────────────────────────────────────
@router.get("/{job_id}/comments")
def list_comments(
    job_id: str,
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
):
    _get_own_job(job_id, current_user, db)
    comments = (
        db.query(models.JobComment)
        .filter_by(job_id=job_id)
        .order_by(models.JobComment.created_at.asc())
        .all()
    )
    return [
        {
            "id": c.id,
            "user_id": c.user_id,
            "user_name": c.user.name if c.user else "",
            "content": c.content,
            "created_at": c.created_at.isoformat() if c.created_at else None,
        }
        for c in comments
    ]


@router.post("/{job_id}/comments")
def add_comment(
    job_id: str,
    body: dict,
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
):
    _get_own_job(job_id, current_user, db)
    content = body.get("content", "").strip()
    if not content:
        raise HTTPException(400, "コメント内容が空です")

    comment = models.JobComment(
        job_id=job_id,
        user_id=current_user.id,
        content=content,
    )
    db.add(comment)
    db.commit()
    db.refresh(comment)
    return {
        "id": comment.id,
        "user_id": comment.user_id,
        "user_name": current_user.name,
        "content": comment.content,
        "created_at": comment.created_at.isoformat() if comment.created_at else None,
    }


@router.put("/{job_id}/archive-and-subscribe")
def archive_and_subscribe(
    job_id: str,
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
):
    """案件を完了・非表示（archived）にし、顧客を定期契約へ移行する"""
    job = _get_own_job(job_id, current_user, db)
    job.pipeline_stage = "archived"
    job.status = "completed"

    if job.customer_id:
        customer = db.query(models.Customer).filter_by(
            id=job.customer_id, company_id=current_user.company_id
        ).first()
        if customer:
            customer.contract_type = "subscription"
            
    db.commit()
    return {"message": "Job archived and customer subscribed successfully"}


# ── Helper ─────────────────────────────────────────────
def _get_own_job(job_id: str, user: models.User, db: Session) -> models.Job:
    """自社の案件のみ操作可能"""
    job = db.query(models.Job).filter_by(job_id=job_id, company_id=user.company_id).first()
    if not job:
        raise HTTPException(404, "案件が見つかりません")
    return job
