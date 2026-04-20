"""管理者ダッシュボードルーター（admin権限のみ）"""
from datetime import datetime, timezone, timedelta
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session
from app.database import get_db
from app import models, auth

router = APIRouter(prefix="/v1/admin", tags=["admin"])


# ── Schemas ────────────────────────────────────────────
class SummaryOut(BaseModel):
    month_sales: int
    month_jobs: int
    conversion_rate: int
    avg_price: int


class DaySales(BaseModel):
    date: str
    sales: int


class StaffRanking(BaseModel):
    user_name: str
    sales: int
    count: int


# ── Endpoints ──────────────────────────────────────────
@router.get("/summary", response_model=SummaryOut)
def get_summary(
    current_user: models.User = Depends(auth.require_admin),
    db: Session = Depends(get_db),
):
    now = datetime.now(timezone.utc)
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    jobs_this_month = (
        db.query(models.Job)
        .filter(
            models.Job.company_id == current_user.company_id,
            models.Job.created_at >= month_start,
        )
        .all()
    )

    month_jobs  = len(jobs_this_month)
    # 不成約 (lost) を売上から除外
    month_sales = sum(j.price_total for j in jobs_this_month if j.status != "lost")
    completed   = sum(1 for j in jobs_this_month if j.status == "completed")
    conversion  = round(completed / month_jobs * 100) if month_jobs > 0 else 0
    avg_price   = round(month_sales / month_jobs) if month_jobs > 0 else 0

    return SummaryOut(
        month_sales=month_sales,
        month_jobs=month_jobs,
        conversion_rate=conversion,
        avg_price=avg_price,
    )


@router.get("/sales-chart", response_model=list[DaySales])
def get_sales_chart(
    days: int = 7,
    current_user: models.User = Depends(auth.require_admin),
    db: Session = Depends(get_db),
):
    now = datetime.now(timezone.utc)
    result = []

    for i in range(days - 1, -1, -1):
        target = now - timedelta(days=i)
        day_start = target.replace(hour=0, minute=0, second=0, microsecond=0)
        day_end   = target.replace(hour=23, minute=59, second=59, microsecond=999999)

        total = (
            db.query(func.sum(models.Job.price_total))
            .filter(
                models.Job.company_id == current_user.company_id,
                models.Job.created_at >= day_start,
                models.Job.created_at <= day_end,
                models.Job.status != "lost"  # 不成約の金額はチャートに含めない
            )
            .scalar()
        ) or 0

        result.append(DaySales(date=target.strftime("%m/%d"), sales=int(total)))

    return result


@router.get("/staff-ranking", response_model=list[StaffRanking])
def get_staff_ranking(
    current_user: models.User = Depends(auth.require_admin),
    db: Session = Depends(get_db),
):
    rows = (
        db.query(
            models.User.name.label("user_name"),
            func.sum(models.Job.price_total).label("sales"),
            func.count(models.Job.job_id).label("count"),
        )
        .join(models.Job, models.Job.user_id == models.User.id)
        .filter(
            models.Job.company_id == current_user.company_id,
            models.Job.status != "lost"  # 不成約の売上を成績に含めない
        )
        .group_by(models.User.id, models.User.name)
        .order_by(func.sum(models.Job.price_total).desc())
        .all()
    )

    return [StaffRanking(user_name=r.user_name, sales=r.sales or 0, count=r.count) for r in rows]
