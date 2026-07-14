"""案件ルーター: 案件CRUD（テナント分離あり）+ パイプライン + 写真"""
import json
import os
import time
import uuid as uuid_mod
from typing import Any
from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File
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
    customer_id: str | None = None
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
            customer_id=j.customer_id,
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
    """営業パイプライン: カンバン形式でステージ別グルーピング（写真データ軽量化）"""
    stages = ["prospect", "inquiry", "estimate", "negotiation", "contract", "scheduled", "waiting_manifest", "completed", "lost"]
    jobs = db.query(models.Job).filter_by(
        company_id=current_user.company_id
    ).order_by(models.Job.updated_at.desc()).all()

    pipeline = {}
    for stage in stages:
        pipeline[stage] = []
    for j in jobs:
        stage = j.pipeline_stage if j.pipeline_stage in stages else "inquiry"
        d = JobOut.from_orm_job(j).model_dump()
        # パイプライン一覧では写真はカウントだけ返す（レスポンス軽量化）
        photo_list = d.get("photos", [])
        d["photo_count"] = len(photo_list) if isinstance(photo_list, list) else 0
        d["photos"] = []  # 一覧ではデータを送らない
        pipeline[stage].append(d)

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

@router.post("/generate-recurring", status_code=200)
def generate_recurring_jobs(
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
):
    from datetime import date, datetime
    from dateutil.relativedelta import relativedelta
    today_str = date.today().isoformat()
    
    # テンプレートを取得
    templates = db.query(models.Job).filter(
        models.Job.company_id == current_user.company_id,
        models.Job.pipeline_stage == "regular_template",
        models.Job.work_date != None,
        models.Job.work_date <= today_str
    ).all()
    
    generated_count = 0
    for tmpl in templates:
        # 新しい案件（作業予定）を作成
        new_job = models.Job(
            company_id=tmpl.company_id,
            user_id=tmpl.user_id,
            job_name=tmpl.job_name,
            customer_name=tmpl.customer_name,
            address=tmpl.address,
            work_date=tmpl.work_date,
            notes=tmpl.notes,
            price_total=tmpl.price_total,
            status="pending",
            pipeline_stage="scheduled", # 作業予定に直接入れる
            job_type=tmpl.job_type,
            assigned_to=tmpl.assigned_to,
            customer_id=tmpl.customer_id,
            form_data=tmpl.form_data, # コンテナ交換等の区分も引き継ぐ
        )
        db.add(new_job)
        
        # テンプレートの次回予定日を1ヶ月後に更新
        try:
            curr_date = datetime.strptime(tmpl.work_date, "%Y-%m-%d").date()
            next_date = curr_date + relativedelta(months=1)
            tmpl.work_date = next_date.isoformat()
        except:
            tmpl.work_date = (date.today() + relativedelta(months=1)).isoformat()
            
        generated_count += 1
        
    if generated_count > 0:
        db.commit()
        
    return {"generated_count": generated_count}


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


# ── Photo Upload ───────────────────────────────────────
@router.post("/{job_id}/photos")
async def upload_job_photos(
    job_id: str,
    images: list[UploadFile] = File(...),
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
):
    """案件に写真をアップロード（base64 DB保存方式 — Renderデプロイでも消えない）"""
    from PIL import Image
    import io, base64

    job = _get_own_job(job_id, current_user, db)

    # 既存の写真リストを取得
    existing = []
    if job.photos:
        try:
            existing = json.loads(job.photos)
        except Exception:
            pass

    new_urls = []
    MAX_SIZE = 1200  # 最大ピクセル（幅or高さ）
    JPEG_QUALITY = 75  # JPEG圧縮品質

    for f in images:
        content = await f.read()
        try:
            img = Image.open(io.BytesIO(content))
            # EXIF回転を適用
            try:
                from PIL import ImageOps
                img = ImageOps.exif_transpose(img)
            except Exception:
                pass
            # リサイズ（アスペクト比維持）
            if img.width > MAX_SIZE or img.height > MAX_SIZE:
                img.thumbnail((MAX_SIZE, MAX_SIZE), Image.LANCZOS)
            # RGBA→RGB変換（JPEG保存のため）
            if img.mode in ('RGBA', 'P'):
                img = img.convert('RGB')
            # JPEG圧縮してbase64エンコード
            buf = io.BytesIO()
            img.save(buf, format='JPEG', quality=JPEG_QUALITY, optimize=True)
            b64 = base64.b64encode(buf.getvalue()).decode('utf-8')
            data_uri = f"data:image/jpeg;base64,{b64}"
            new_urls.append(data_uri)
        except Exception as e:
            # 画像処理に失敗した場合はそのままbase64化
            b64 = base64.b64encode(content).decode('utf-8')
            mime = f.content_type or "image/jpeg"
            data_uri = f"data:{mime};base64,{b64}"
            new_urls.append(data_uri)

    existing.extend(new_urls)
    job.photos = json.dumps(existing)
    db.commit()

    return {"uploaded": len(new_urls), "total": len(existing), "urls": ["(base64 stored)"] * len(new_urls)}


# ── 壊れた写真参照のクリーンアップ ──────────────────────
@router.post("/cleanup-broken-photos")
def cleanup_broken_photos(
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
):
    """壊れた /uploads/... パスの写真参照を一括削除"""
    jobs = db.query(models.Job).filter_by(company_id=current_user.company_id).all()
    cleaned_count = 0
    for j in jobs:
        if not j.photos:
            continue
        try:
            photos = json.loads(j.photos)
        except Exception:
            continue
        if not isinstance(photos, list):
            continue
        # /uploads/ で始まるパスは壊れているので除外、data: や https:// は残す
        valid = [p for p in photos if not str(p).startswith('/uploads/')]
        if len(valid) != len(photos):
            j.photos = json.dumps(valid)
            cleaned_count += 1
    db.commit()
    return {"message": f"{cleaned_count} 件の案件から壊れた写真参照を削除しました"}


# ── Helper ─────────────────────────────────────────────
def _get_own_job(job_id: str, user: models.User, db: Session) -> models.Job:
    """自社の案件のみ操作可能"""
    job = db.query(models.Job).filter_by(job_id=job_id, company_id=user.company_id).first()
    if not job:
        raise HTTPException(404, "案件が見つかりません")
    return job



from fastapi import File, UploadFile, Form
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email.utils import formataddr
from email import encoders
from email.header import Header
import smtplib
import os

@router.post("/{job_id}/send-estimate")
async def send_estimate_email(
    job_id: str,
    subject: str = Form(...),
    body: str = Form(...),
    file: UploadFile = File(...),
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db)
):
    job = db.query(models.Job).filter_by(id=job_id, company_id=current_user.company_id).first()
    if not job:
        raise HTTPException(404, "案件が見つかりません")
        
    customer = db.query(models.Customer).filter_by(id=job.customer_id).first()
    if not customer or not customer.email:
        raise HTTPException(400, "顧客のメールアドレスが登録されていません")
        
    company = db.query(models.Company).filter_by(id=current_user.company_id).first()
    settings = db.query(models.CompanySettings).filter_by(company_id=current_user.company_id).first()

    smtp_host = settings.smtp_host if settings and settings.smtp_host else os.getenv("SMTP_HOST", "smtp.resend.com")
    smtp_port = settings.smtp_port if settings and settings.smtp_port else int(os.getenv("SMTP_PORT", "465"))
    smtp_user = settings.smtp_user if settings and settings.smtp_user else os.getenv("SMTP_USER", "")
    smtp_pass = settings.smtp_password if settings and settings.smtp_password else os.getenv("SMTP_PASS", "")

    if not smtp_pass:
        raise HTTPException(400, "SMTP設定が未設定です。")

    from_email = settings.smtp_from_email if settings and settings.smtp_from_email else smtp_user

    auth_user = smtp_user
    reply_to = os.getenv("REPLY_TO_EMAIL", None)
    if 'resend.com' in smtp_host:
        auth_user = 'resend'
        if '@' in (smtp_user or '') and smtp_user != from_email:
            reply_to = smtp_user
    else:
        if not reply_to and '@' in (smtp_user or '') and settings and settings.smtp_from_email and smtp_user != settings.smtp_from_email:
            reply_to = smtp_user

    msg = MIMEMultipart()
    msg['From'] = formataddr((str(Header(company.name, 'utf-8')), from_email))
    msg['To'] = customer.email
    msg['Subject'] = subject
    if reply_to:
        msg['Reply-To'] = reply_to
        
    body_text = body.replace('\\n', '\n')
    msg.attach(MIMEText(body_text, 'plain'))

    pdf_bytes = await file.read()
    part = MIMEBase('application', 'pdf')
    part.set_payload(pdf_bytes)
    encoders.encode_base64(part)
    filename = f"Estimate_{customer.name}.pdf".replace(" ", "_")
    part.add_header('Content-Disposition', 'attachment', filename=filename)
    msg.attach(part)

    try:
        if smtp_port == 465:
            server = smtplib.SMTP_SSL(smtp_host, smtp_port, timeout=15)
        else:
            server = smtplib.SMTP(smtp_host, smtp_port, timeout=15)
            server.starttls()
        server.login(auth_user, smtp_pass)
        server.send_message(msg)
        server.quit()
    except Exception as e:
        raise HTTPException(500, f"メール送信に失敗しました: {e}")

    # 監査ログ
    audit = models.AuditLog(
        company_id=current_user.company_id,
        user_id=current_user.id,
        user_name=current_user.username,
        action="email_sent",
        target_type="job_estimate",
        target_id=job.id,
        details=f"見積書メール送信: {customer.name} → {customer.email}",
    )
    db.add(audit)
    db.commit()

    return {"status": "ok"}
