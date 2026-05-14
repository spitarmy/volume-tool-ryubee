"""営業共有カレンダールーター"""
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import or_, and_
from app.database import get_db
from app import models, auth

router = APIRouter(prefix="/v1/calendar", tags=["calendar"])

# ── Schemas ────────────────────────────────────────────
class EventCreate(BaseModel):
    title: str
    event_date: str
    end_date: str | None = None
    start_time: str | None = None
    end_time: str | None = None
    color: str = "#3B82F6"
    memo: str = ""
    all_day: bool = False
    is_done: bool = False
    user_id: str | None = None


class EventUpdate(EventCreate):
    pass


class EventOut(BaseModel):
    id: str
    title: str
    event_date: str
    end_date: str | None
    start_time: str | None
    end_time: str | None
    color: str
    memo: str
    all_day: bool
    is_done: bool
    user_id: str | None
    user_name: str = ""

    model_config = {"from_attributes": True}


# ── Endpoints ──────────────────────────────────────────
@router.get("/events", response_model=list[EventOut])
def get_events(
    month: str = Query(...),  # YYYY-MM
    user_filter: str | None = None,  # 特定のユーザーIDで絞り込み
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
):
    """指定月のイベント一覧を取得"""
    # Filter: event_date is in the month, OR end_date is in the month, OR the month is between event_date and end_date
    next_month = f"{month[:5]}{(int(month[5:]) % 12) + 1:02d}"
    if month.endswith("-12"):
        next_month = f"{int(month[:4]) + 1}-01"
    
    # 予定がその月に被っているか
    # event_date < next_month AND (end_date >= month OR end_date IS NULL AND event_date >= month)
    # 簡略化して: event_date が month と一致、または end_date がある場合はその期間が month と被る
    query = db.query(models.CalendarEvent).filter(
        models.CalendarEvent.company_id == current_user.company_id,
        or_(
            models.CalendarEvent.event_date.startswith(month),
            and_(
                models.CalendarEvent.end_date != None,
                models.CalendarEvent.event_date <= f"{month}-31",
                models.CalendarEvent.end_date >= f"{month}-01"
            )
        )
    )

    if user_filter:
        query = query.filter(
            or_(
                models.CalendarEvent.user_id == user_filter,
                models.CalendarEvent.user_id == None  # 担当未定/全員共通も含む
            )
        )

    events = query.all()
    
    result = []
    for e in events:
        out = EventOut.model_validate(e)
        if e.user:
            out.user_name = e.user.name
        result.append(out)

    return result


@router.post("/events", response_model=EventOut)
def create_event(
    body: EventCreate,
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
):
    event = models.CalendarEvent(
        company_id=current_user.company_id,
        title=body.title,
        event_date=body.event_date,
        end_date=body.end_date,
        start_time=body.start_time,
        end_time=body.end_time,
        color=body.color,
        memo=body.memo,
        all_day=body.all_day,
        is_done=body.is_done,
        user_id=body.user_id,
    )
    db.add(event)
    db.commit()
    db.refresh(event)

    out = EventOut.model_validate(event)
    if event.user:
        out.user_name = event.user.name
    return out


@router.put("/events/{event_id}", response_model=EventOut)
def update_event(
    event_id: str,
    body: EventUpdate,
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
):
    event = db.query(models.CalendarEvent).filter_by(
        id=event_id, company_id=current_user.company_id
    ).first()
    
    if not event:
        raise HTTPException(status_code=404, detail="イベントが見つかりません")

    event.title = body.title
    event.event_date = body.event_date
    event.end_date = body.end_date
    event.start_time = body.start_time
    event.end_time = body.end_time
    event.color = body.color
    event.memo = body.memo
    event.all_day = body.all_day
    event.is_done = body.is_done
    event.user_id = body.user_id

    db.commit()
    db.refresh(event)

    out = EventOut.model_validate(event)
    if event.user:
        out.user_name = event.user.name
    return out


@router.delete("/events/{event_id}")
def delete_event(
    event_id: str,
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
):
    event = db.query(models.CalendarEvent).filter_by(
        id=event_id, company_id=current_user.company_id
    ).first()
    
    if not event:
        raise HTTPException(status_code=404, detail="イベントが見つかりません")

    db.delete(event)
    db.commit()
    return {"success": True}
