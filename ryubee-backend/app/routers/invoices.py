"""請求書ルーター: 請求書CRUD・月次一括生成・未入金アラート"""
import os
import json
import base64
from datetime import datetime, date
from typing import Any
from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File, Form, Response
from pydantic import BaseModel
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import func
from openai import AsyncOpenAI
from app.database import get_db
from app import models, auth
from jinja2 import Environment, FileSystemLoader
import weasyprint
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email.mime.text import MIMEText
from email import encoders
from email.utils import formataddr
from email.header import Header

router = APIRouter(prefix="/v1/invoices", tags=["invoices"])


# ── Schemas ────────────────────────────────────────────
class InvoiceItemCreate(BaseModel):
    description: str = ""
    quantity: float = 1
    unit: str = "式"
    unit_price: float = 0
    amount: int = 0
    manifest_id: str | None = None


class InvoiceCreate(BaseModel):
    customer_id: str
    month: str  # YYYY-MM
    total_amount: int = 0
    tax_amount: int = 0
    status: str = "draft"
    due_date: str | None = None
    notes: str = ""
    items: list[InvoiceItemCreate] = []


class InvoiceUpdate(BaseModel):
    status: str | None = None
    total_amount: int | None = None
    tax_amount: int | None = None
    due_date: str | None = None
    notes: str | None = None
    sent_at: str | None = None


class InvoiceItemOut(BaseModel):
    id: str
    description: str
    quantity: float
    unit: str
    unit_price: float
    amount: int
    manifest_id: str | None
    model_config = {"from_attributes": True}


class PaymentOut(BaseModel):
    id: str
    amount: int
    payment_date: str
    payment_method: str
    notes: str
    created_at: str
    model_config = {"from_attributes": True}


class InvoiceOut(BaseModel):
    id: str
    company_id: str
    customer_id: str
    customer_name: str = ""
    month: str
    total_amount: int
    tax_amount: int
    status: str
    due_date: str | None
    sent_at: str | None
    notes: str
    freee_synced: bool
    items: list[InvoiceItemOut] = []
    payments: list[PaymentOut] = []
    paid_total: int = 0
    created_at: str
    updated_at: str
    model_config = {"from_attributes": True}


class MonthlyGenerateRequest(BaseModel):
    month: str  # YYYY-MM
    due_date: str | None = None


class CustomCustomerInvoiceData(BaseModel):
    customer_id: str
    base_price: int
    add_item_name: str = ""
    add_item_price: int = 0
    notes: str = ""


class CustomMonthlyGenerateRequest(BaseModel):
    month: str
    due_date: str | None = None
    customers: list[CustomCustomerInvoiceData]


class UnpaidAlertOut(BaseModel):
    invoice_id: str
    customer_id: str
    customer_name: str
    month: str
    total_amount: int
    paid_total: int
    remaining: int
    due_date: str | None
    is_fiscal_crossover: bool  # 決算跨ぎ売掛金フラグ
    days_overdue: int
    email: str | None = None
    last_reminded_at: str | None = None
    consecutive_unpaid_count: int = 1  # 連続未納回数


class CarryoverRequest(BaseModel):
    source_month: str  # 繰越元月 YYYY-MM
    target_month: str  # 繰越先月 YYYY-MM


# ── Helpers ────────────────────────────────────────────
def _invoice_to_out(inv: models.Invoice) -> InvoiceOut:
    paid = sum(p.amount for p in inv.payments)
    cname = inv.customer.name if inv.customer else ""
    return InvoiceOut(
        id=inv.id,
        company_id=inv.company_id,
        customer_id=inv.customer_id,
        customer_name=cname,
        month=inv.month,
        total_amount=inv.total_amount,
        tax_amount=inv.tax_amount,
        status=inv.status,
        due_date=inv.due_date,
        sent_at=inv.sent_at,
        notes=inv.notes,
        freee_synced=inv.freee_synced,
        items=[InvoiceItemOut(
            id=it.id, description=it.description, quantity=it.quantity,
            unit=it.unit, unit_price=it.unit_price, amount=it.amount,
            manifest_id=it.manifest_id,
        ) for it in inv.items],
        payments=[PaymentOut(
            id=p.id, amount=p.amount, payment_date=p.payment_date,
            payment_method=p.payment_method, notes=p.notes,
            created_at=p.created_at.isoformat(),
        ) for p in inv.payments],
        paid_total=paid,
        created_at=inv.created_at.isoformat(),
        updated_at=inv.updated_at.isoformat(),
    )


# ── Endpoints ──────────────────────────────────────────
@router.get("", response_model=list[InvoiceOut])
def list_invoices(
    month: str | None = Query(None),
    status: str | None = Query(None),
    customer_id: str | None = Query(None),
    limit: int = Query(1000, ge=1, le=5000),
    offset: int = Query(0, ge=0),
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
):
    q = db.query(models.Invoice).options(
        joinedload(models.Invoice.items),
        joinedload(models.Invoice.payments),
        joinedload(models.Invoice.customer),
    ).filter_by(company_id=current_user.company_id)
    if month:
        q = q.filter(models.Invoice.month == month)
    if status:
        q = q.filter(models.Invoice.status == status)
    if customer_id:
        q = q.filter(models.Invoice.customer_id == customer_id)
    invoices = q.order_by(models.Invoice.month.desc(), models.Invoice.created_at.desc()).offset(offset).limit(limit).all()
    # deduplicate due to joinedload
    seen = set()
    unique = []
    for inv in invoices:
        if inv.id not in seen:
            seen.add(inv.id)
            unique.append(inv)
    return [_invoice_to_out(i) for i in unique]


@router.post("", response_model=InvoiceOut, status_code=201)
def create_invoice(
    body: InvoiceCreate,
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
):
    cust = db.query(models.Customer).filter_by(
        id=body.customer_id, company_id=current_user.company_id
    ).first()
    if not cust:
        raise HTTPException(404, "顧客が見つかりません")

    inv = models.Invoice(
        company_id=current_user.company_id,
        customer_id=body.customer_id,
        month=body.month,
        total_amount=body.total_amount,
        tax_amount=body.tax_amount,
        status=body.status,
        due_date=body.due_date,
        notes=body.notes,
    )
    db.add(inv)
    db.flush()

    for item in body.items:
        db.add(models.InvoiceItem(
            invoice_id=inv.id,
            description=item.description,
            quantity=item.quantity,
            unit=item.unit,
            unit_price=item.unit_price,
            amount=item.amount,
            manifest_id=item.manifest_id,
        ))

    db.commit()
    db.refresh(inv)
    inv = db.query(models.Invoice).options(
        joinedload(models.Invoice.items),
        joinedload(models.Invoice.payments),
        joinedload(models.Invoice.customer),
    ).filter_by(id=inv.id).first()
    return _invoice_to_out(inv)


client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY", "dummy_key_to_prevent_crash"))

OCR_SYSTEM_PROMPT = """
あなたは、手書きのゴミ回収伝票・集計表（例：花のいえ）から数値を読み取るOCR AIです。
以下のルールに厳密に従って、合計量（重量kgまたは袋数）を読み取り、JSON形式で出力してください。

【出力仕様】
{
  "total_quantity": 5345, // 読み取った合計数値（数値型）
  "unit": "kg", // kg または 袋
  "notes": "花のいえ集計表より読み取り" // 任意の読み取りメモ
}

- もし画像の「合計」欄に重量（例: 5345kg）と袋数の両方がある場合は、重量(kg)を優先して `total_quantity` とし、`unit` を "kg" にしてください。
- 合計欄がない場合は、読み取れる全行の数値を足し合わせて合計を算出してください。
- マークダウン(```json 等)を使用しないでください。パース可能な「生のJSONテキスト」のみを出力してください。
"""

@router.post("/ocr-create", response_model=InvoiceOut, status_code=201)
async def create_ocr_invoice(
    customer_id: str = Form(...),
    image: UploadFile = File(...),
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
):
    cust = db.query(models.Customer).filter_by(
        id=customer_id, company_id=current_user.company_id
    ).first()
    if not cust:
        raise HTTPException(404, "顧客が見つかりません")

    content = await image.read()
    b64 = base64.b64encode(content).decode('utf-8')
    mime_type = image.content_type or "image/jpeg"
    b64_url = f"data:{mime_type};base64,{b64}"

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key or not api_key.startswith("sk-"):
        raise HTTPException(500, "OpenAI API Keyが設定されていません")

    messages = [
        {"role": "system", "content": OCR_SYSTEM_PROMPT},
        {"role": "user", "content": [
            {"type": "text", "text": "この集計表の合計量を読み取ってください。"},
            {"type": "image_url", "image_url": {"url": b64_url}}
        ]}
    ]

    try:
        response = await client.chat.completions.create(
            model="gpt-4o",
            messages=messages,
            response_format={"type": "json_object"},
            max_tokens=600,
            temperature=0.1
        )
        ai_content = response.choices[0].message.content
        ai_result = json.loads(ai_content)
    except Exception as e:
        print(f"OpenAI API Error: {e}")
        raise HTTPException(500, "AI画像読み取りに失敗しました")

    total_qty = float(ai_result.get("total_quantity", 0))
    unit = ai_result.get("unit", "式")
    notes = ai_result.get("notes", "写真からAI自動読み取り")

    # 単価は一旦0で設定し、ユーザーが編集できるようにする
    unit_price = 0
    now = date.today()
    month = f"{now.year}-{now.month:02d}"
    due_date_str = _auto_due_date(cust, month)

    amount = int(total_qty * unit_price)
    tax = int(amount * 0.1)

    inv = models.Invoice(
        company_id=current_user.company_id,
        customer_id=customer_id,
        month=month,
        total_amount=amount + tax,
        tax_amount=tax,
        status="draft",
        due_date=due_date_str,
        notes=f"【AI OCR自動作成】\n抽出結果: {total_qty}{unit}\nAIメモ: {notes}",
    )
    db.add(inv)
    db.flush()

    db.add(models.InvoiceItem(
        invoice_id=inv.id,
        description=f"回収費用 ({total_qty}{unit})",
        quantity=total_qty,
        unit=unit,
        unit_price=unit_price,
        amount=amount,
    ))

    db.commit()
    db.refresh(inv)
    inv = db.query(models.Invoice).options(
        joinedload(models.Invoice.items),
        joinedload(models.Invoice.payments),
        joinedload(models.Invoice.customer),
    ).filter_by(id=inv.id).first()
    return _invoice_to_out(inv)


@router.get("/unpaid-alerts", response_model=list[UnpaidAlertOut])
def unpaid_alerts(
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
):
    """未入金アラート: 業者別締め払い日を考慮して未払い請求書を返す"""
    settings = db.query(models.CompanySettings).filter_by(
        company_id=current_user.company_id
    ).first()
    fiscal_end_month = settings.fiscal_year_end_month if settings else 3

    invoices = db.query(models.Invoice).options(
        joinedload(models.Invoice.payments),
        joinedload(models.Invoice.customer),
    ).filter(
        models.Invoice.company_id == current_user.company_id,
        models.Invoice.status.in_(["sent", "partial", "overdue", "draft"]),
    ).all()

    seen = set()
    unique = []
    for inv in invoices:
        if inv.id not in seen:
            seen.add(inv.id)
            unique.append(inv)

    today = date.today()
    alerts = []
    for inv in unique:
        paid = sum(p.amount for p in inv.payments)
        remaining = inv.total_amount - paid
        if remaining <= 0:
            continue

        # 業者別の支払期限を算出
        customer_due = _calc_customer_due_date(inv, inv.customer)

        # 支払期限前の請求書はアラート対象外
        if customer_due and today <= customer_due:
            continue

        days_overdue = 0
        if customer_due:
            days_overdue = (today - customer_due).days

        is_crossover = False
        try:
            inv_year, inv_month = int(inv.month[:4]), int(inv.month[5:7])
            if fiscal_end_month >= inv_month:
                fiscal_year_end = date(inv_year, fiscal_end_month, 28)
            else:
                fiscal_year_end = date(inv_year + 1, fiscal_end_month, 28)
            if today > fiscal_year_end:
                is_crossover = True
        except (ValueError, IndexError):
            pass

        cname = inv.customer.name if inv.customer else ""
        cemail = inv.customer.email if inv.customer else None
        alerts.append(UnpaidAlertOut(
            invoice_id=inv.id,
            customer_id=inv.customer_id,
            customer_name=cname,
            month=inv.month,
            total_amount=inv.total_amount,
            paid_total=paid,
            remaining=remaining,
            due_date=customer_due.isoformat() if customer_due else inv.due_date,
            is_fiscal_crossover=is_crossover,
            days_overdue=days_overdue,
            email=cemail,
            last_reminded_at=inv.last_reminded_at,
        ))

    alerts.sort(key=lambda a: (-int(a.is_fiscal_crossover), -a.days_overdue))

    # 連続未納回数を計算（同一顧客の未払い月数）
    from collections import Counter
    customer_unpaid_months = Counter()
    for a in alerts:
        customer_unpaid_months[a.customer_id] += 1
    for a in alerts:
        a.consecutive_unpaid_count = customer_unpaid_months[a.customer_id]

    return alerts


def _calc_customer_due_date(inv: models.Invoice, customer) -> date | None:
    """業者の締め払い設定に基づいて支払期限を計算"""
    if not customer:
        if inv.due_date:
            try:
                return datetime.strptime(inv.due_date, "%Y-%m-%d").date()
            except ValueError:
                pass
        return None

    try:
        inv_year, inv_month = int(inv.month[:4]), int(inv.month[5:7])
    except (ValueError, IndexError):
        return None

    offset = getattr(customer, 'payment_due_month_offset', 1) or 1
    due_day = getattr(customer, 'payment_due_day', 31) or 31

    pay_month = inv_month + offset
    pay_year = inv_year
    while pay_month > 12:
        pay_month -= 12
        pay_year += 1

    import calendar
    last_day = calendar.monthrange(pay_year, pay_month)[1]
    actual_due_day = min(due_day, last_day)

    return date(pay_year, pay_month, actual_due_day)


@router.get("/{invoice_id}", response_model=InvoiceOut)
def get_invoice(
    invoice_id: str,
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
):
    inv = db.query(models.Invoice).options(
        joinedload(models.Invoice.items),
        joinedload(models.Invoice.payments),
        joinedload(models.Invoice.customer),
    ).filter_by(id=invoice_id, company_id=current_user.company_id).first()
    if not inv:
        raise HTTPException(404, "請求書が見つかりません")
    return _invoice_to_out(inv)


@router.post("/bulk-delete")
def bulk_delete_invoices(
    body: dict,
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
):
    invoice_ids = body.get("invoice_ids", [])
    if not invoice_ids:
        return {"message": "No invoices provided"}
    db.query(models.InvoiceItem).filter(
        models.InvoiceItem.invoice_id.in_(invoice_ids)
    ).delete(synchronize_session=False)
    db.query(models.Payment).filter(
        models.Payment.invoice_id.in_(invoice_ids)
    ).delete(synchronize_session=False)
    db.query(models.Invoice).filter(
        models.Invoice.company_id == current_user.company_id,
        models.Invoice.id.in_(invoice_ids)
    ).delete(synchronize_session=False)
    db.commit()
    return {"message": f"{len(invoice_ids)} invoices deleted"}


@router.put("/{invoice_id}", response_model=InvoiceOut)
def update_invoice(
    invoice_id: str,
    body: InvoiceUpdate,
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
):
    inv = db.query(models.Invoice).filter_by(
        id=invoice_id, company_id=current_user.company_id
    ).first()
    if not inv:
        raise HTTPException(404, "請求書が見つかりません")
    for field, val in body.model_dump(exclude_none=True).items():
        setattr(inv, field, val)
    db.commit()
    db.refresh(inv)
    inv = db.query(models.Invoice).options(
        joinedload(models.Invoice.items),
        joinedload(models.Invoice.payments),
        joinedload(models.Invoice.customer),
    ).filter_by(id=inv.id).first()
    return _invoice_to_out(inv)


class InvoiceFullUpdate(BaseModel):
    total_amount: int | None = None
    tax_amount: int | None = None
    status: str | None = None
    due_date: str | None = None
    notes: str | None = None
    sent_at: str | None = None
    items: list[InvoiceItemCreate] | None = None


@router.put("/{invoice_id}/full", response_model=InvoiceOut)
def update_invoice_full(
    invoice_id: str,
    body: InvoiceFullUpdate,
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
):
    """請求書のトップレベル情報＋明細を一括更新"""
    inv = db.query(models.Invoice).options(
        joinedload(models.Invoice.items),
    ).filter_by(
        id=invoice_id, company_id=current_user.company_id
    ).first()
    if not inv:
        raise HTTPException(404, "請求書が見つかりません")

    data = body.model_dump(exclude_none=True)
    items_data = data.pop("items", None)

    for field, val in data.items():
        setattr(inv, field, val)

    if items_data is not None:
        # 既存明細を全削除
        for old_item in inv.items:
            db.delete(old_item)
        db.flush()
        # 新しい明細を追加
        subtotal = 0
        for item in items_data:
            amt = item.get("amount", 0) or int(float(item.get("quantity", 1)) * float(item.get("unit_price", 0)))
            db.add(models.InvoiceItem(
                invoice_id=inv.id,
                description=item.get("description", ""),
                quantity=item.get("quantity", 1),
                unit=item.get("unit", "式"),
                unit_price=item.get("unit_price", 0),
                amount=amt,
                manifest_id=item.get("manifest_id"),
            ))
            subtotal += amt
        # 合計再計算
        tax = int(subtotal * 0.1)
        inv.total_amount = subtotal + tax
        inv.tax_amount = tax

    db.commit()
    db.refresh(inv)
    inv = db.query(models.Invoice).options(
        joinedload(models.Invoice.items),
        joinedload(models.Invoice.payments),
        joinedload(models.Invoice.customer),
    ).filter_by(id=inv.id).first()
    return _invoice_to_out(inv)


@router.post("/generate-monthly", response_model=list[InvoiceOut])
def generate_monthly_invoices(
    body: MonthlyGenerateRequest,
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
):
    """指定月の産廃マニフェスト（重量課金）に基づいて請求書を一括生成"""
    company_id = current_user.company_id
    month = body.month  # YYYY-MM

    # この月に発行された産廃マニフェストを取得
    customers = db.query(models.Customer).filter_by(company_id=company_id).all()
    c_ids = [c.id for c in customers]
    c_map = {c.id: c for c in customers}
    if not c_ids:
        return []

    manifests = db.query(models.Manifest).filter(
        models.Manifest.customer_id.in_(c_ids),
        models.Manifest.issue_date.like(f"{month}%"),
    ).all()

    # この月に完了した一般案件（産廃マニフェスト以外）も取得
    jobs = db.query(models.Job).filter(
        models.Job.customer_id.in_(c_ids),
        models.Job.work_date.like(f"{month}%")
    ).all()

    # 顧客ごとにグルーピング
    from collections import defaultdict
    cust_manifests: dict[str, list[models.Manifest]] = defaultdict(list)
    cust_jobs: dict[str, list[models.Job]] = defaultdict(list)
    for m in manifests:
        cust_manifests[m.customer_id].append(m)
    for j in jobs:
        cust_jobs[j.customer_id].append(j)

    # 処理対象の顧客IDリスト
    target_cust_ids = set(list(cust_manifests.keys()) + list(cust_jobs.keys()))
    for c in customers:
        if c.contract_type == "subscription":
            target_cust_ids.add(c.id)

    created = []
    
    # 前月計算ロジック
    import datetime
    import calendar
    import json
    from dateutil.relativedelta import relativedelta
    try:
        curr_d = datetime.datetime.strptime(month, "%Y-%m").date()
        prev_d = curr_d - relativedelta(months=1)
        prev_month_str = prev_d.strftime("%Y-%m")
    except Exception:
        prev_month_str = ""

    for cust_id in target_cust_ids:
        # 既存請求書チェック（重複防止）
        existing = db.query(models.Invoice).filter_by(
            company_id=company_id, customer_id=cust_id, month=month
        ).first()
        if existing:
            continue

        items = []
        sales_total = 0
        
        # 産廃マニフェスト分
        for m in cust_manifests.get(cust_id, []):
            if m.weight_kg and m.unit_price_per_kg:
                amt = int(m.weight_kg * m.unit_price_per_kg)
            else:
                amt = 0
            # weight_kgが設定されているもののみ請求対象とする
            if amt > 0:
                items.append(models.InvoiceItem(
                    description=f"産廃: {m.waste_type or '廃棄物'} ({m.weight_kg or 0}kg) [No.{m.manifest_number}]",
                    quantity=m.weight_kg or 0,
                    unit="kg",
                    unit_price=m.unit_price_per_kg or 0,
                    amount=amt,
                    manifest_id=m.id,
                ))
                sales_total += amt

        # 一般案件分
        for j in cust_jobs.get(cust_id, []):
            j_amt = j.final_price or j.estimated_price or j.price_total or 0
            if j_amt > 0:
                items.append(models.InvoiceItem(
                    description=f"案件: {j.job_name or '回収作業'}",
                    quantity=1,
                    unit="式",
                    unit_price=j_amt,
                    amount=j_amt,
                ))
                sales_total += j_amt

                if j.discount_amount and j.discount_amount > 0:
                    items.append(models.InvoiceItem(
                        description="値引き", quantity=1, unit="式",
                        unit_price=-j.discount_amount, amount=-j.discount_amount
                    ))
                    sales_total -= j.discount_amount

                if j.surcharge_amount and j.surcharge_amount > 0:
                    items.append(models.InvoiceItem(
                        description="追加料金", quantity=1, unit="式",
                        unit_price=j.surcharge_amount, amount=j.surcharge_amount
                    ))
                    sales_total += j.surcharge_amount

        # 一般廃棄物（定期契約）の固定月額・日割り計算
        c = c_map.get(cust_id)
        if c and c.contract_type == "subscription":
            try:
                fd = json.loads(c.form_data) if c.form_data else {}
                pricing_list = fd.get("pricing_list", [])
                end_date_str = fd.get("collection_end_date", "")
            except:
                pricing_list = []
                end_date_str = ""

            if pricing_list:
                closing_day = c.billing_closing_day or 31
                try:
                    c_year, c_month = int(month[:4]), int(month[5:7])
                    if closing_day >= 28:
                        _, last_day = calendar.monthrange(c_year, c_month)
                        p_start = datetime.date(c_year, c_month, 1)
                        p_end = datetime.date(c_year, c_month, last_day)
                    else:
                        p_end = datetime.date(c_year, c_month, closing_day)
                        if c_month == 1:
                            p_start = datetime.date(c_year - 1, 12, closing_day + 1)
                        else:
                            p_start = datetime.date(c_year, c_month - 1, closing_day + 1)
                except Exception:
                    p_start, p_end = None, None

                end_date = None
                if end_date_str:
                    try:
                        end_date = datetime.datetime.strptime(end_date_str, "%Y-%m-%d").date()
                    except:
                        pass

                if p_start and p_end:
                    should_charge_fixed = True
                    ratio = 1.0

                    if end_date and end_date < p_start:
                        should_charge_fixed = False
                    elif end_date and end_date <= p_end:
                        active_days = (end_date - p_start).days + 1
                        total_days = (p_end - p_start).days + 1
                        ratio = max(0.0, min(1.0, active_days / total_days))

                    if should_charge_fixed:
                        for p in pricing_list:
                            raw_price = float(p.get("price", 0))
                            if raw_price > 0:
                                prorated = int(raw_price * ratio)
                                desc = p.get("item", "定期回収諸費用")
                                if ratio < 1.0:
                                    desc += f" (日割: {p_start.strftime('%m/%d')}〜{end_date.strftime('%m/%d')})"
                                
                                items.append(models.InvoiceItem(
                                    description=desc,
                                    quantity=1,
                                    unit=p.get("unit", "式"),
                                    unit_price=prorated,
                                    amount=prorated,
                                ))
                                sales_total += prorated

        # 売上がなければスキップ（ただし繰越だけあるパターンは今回考慮外とする）
        if sales_total <= 0:
            continue

        # 前月繰越の計算
        carry_over = 0
        if prev_month_str:
            prev_inv = db.query(models.Invoice).options(joinedload(models.Invoice.payments)).filter_by(
                company_id=company_id, customer_id=cust_id, month=prev_month_str
            ).first()
            if prev_inv:
                paid = sum(p.amount for p in prev_inv.payments)
                carry_over_calc = prev_inv.total_amount - paid
                if carry_over_calc > 0:
                    carry_over = carry_over_calc
                    # 繰越項目として追加 (非課税扱いのため sales_totalには入れない)
                    items.append(models.InvoiceItem(
                        description="前回繰越額",
                        quantity=1,
                        unit="式",
                        unit_price=carry_over,
                        amount=carry_over,
                    ))

        tax = int(sales_total * 0.1)
        # 最終請求額 = 当月売上 + 当月消費税 + 前回繰越額
        grand_total = sales_total + tax + carry_over

        customer_fd = {}
        if c_map.get(cust_id) and c_map.get(cust_id).form_data:
            try:
                customer_fd = json.loads(c_map.get(cust_id).form_data)
            except:
                pass
        persistent_note = customer_fd.get("persistent_invoice_note", "")

        notes_text = f"【内訳】今回請求額: ¥{(sales_total+tax):,}, 前回繰越: ¥{carry_over:,}" if carry_over > 0 else "月次一括生成"
        if persistent_note:
            notes_text += f"\n\n{persistent_note}"

        inv = models.Invoice(
            company_id=company_id,
            customer_id=cust_id,
            month=month,
            total_amount=grand_total,
            tax_amount=tax,
            status="draft",
            due_date=body.due_date or _auto_due_date(c_map[cust_id], month),
            notes=notes_text,
        )
        db.add(inv)
        db.flush()

        for item in items:
            item.invoice_id = inv.id
            db.add(item)

        created.append(inv)

    db.commit()

    result = []
    for inv in created:
        loaded = db.query(models.Invoice).options(
            joinedload(models.Invoice.items),
            joinedload(models.Invoice.payments),
            joinedload(models.Invoice.customer),
        ).filter_by(id=inv.id).first()
        result.append(_invoice_to_out(loaded))

    return result


@router.post("/generate-subscriptions-custom", response_model=list[InvoiceOut])
def generate_custom_subscriptions(
    body: CustomMonthlyGenerateRequest,
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
):
    """指定された定期顧客情報を元にカスタム一括請求書を生成"""
    try:
        company_id = current_user.company_id
        month = body.month

        # Get Customer map
        cust_ids = [c.customer_id for c in body.customers]
        customers = db.query(models.Customer).filter(models.Customer.id.in_(cust_ids)).filter_by(company_id=company_id).all()
        c_map = {c.id: c for c in customers}
        
        existing = db.query(models.Invoice).filter(
            models.Invoice.company_id == company_id,
            models.Invoice.month == month,
            models.Invoice.customer_id.in_(cust_ids)
        ).all()
        existing_map = {i.customer_id: i for i in existing}

        created = []
        import datetime
        from dateutil.relativedelta import relativedelta
        try:
            curr_d = datetime.datetime.strptime(month, "%Y-%m").date()
            prev_d = curr_d - relativedelta(months=1)
            prev_month_str = prev_d.strftime("%Y-%m")
        except Exception:
            prev_month_str = ""

        for cust_data in body.customers:
            cust_id = cust_data.customer_id
            if cust_id in existing_map:
                continue
                
            c = c_map.get(cust_id)
            if not c:
                continue
                
            items = []
            sales_total = 0
            
            if cust_data.base_price > 0:
                items.append(models.InvoiceItem(
                    description="定期回収諸費用",
                    quantity=1, unit="式", unit_price=cust_data.base_price, amount=cust_data.base_price
                ))
                sales_total += cust_data.base_price
                
            if cust_data.add_item_name and cust_data.add_item_price > 0:
                items.append(models.InvoiceItem(
                    description=cust_data.add_item_name,
                    quantity=1, unit="式", unit_price=cust_data.add_item_price, amount=cust_data.add_item_price
                ))
                sales_total += cust_data.add_item_price

            if sales_total <= 0:
                continue
                
            carry_over = 0
            if prev_month_str:
                prev_inv = db.query(models.Invoice).options(joinedload(models.Invoice.payments)).filter_by(
                    company_id=company_id, customer_id=cust_id, month=prev_month_str
                ).first()
                if prev_inv:
                    paid = sum(p.amount for p in prev_inv.payments)
                    if prev_inv.total_amount - paid > 0:
                        carry_over = prev_inv.total_amount - paid
                        items.append(models.InvoiceItem(
                            description="前回繰越額", quantity=1, unit="式", unit_price=carry_over, amount=carry_over
                        ))
            
            tax = int(sales_total * 0.1)
            grand_total = sales_total + tax + carry_over

            customer_fd = {}
            if c.form_data:
                import json
                try: customer_fd = json.loads(c.form_data)
                except: pass
            persistent_note = customer_fd.get("persistent_invoice_note", "")

            notes_text = f"【内訳】今回請求額: ¥{(sales_total+tax):,}, 前回繰越: ¥{carry_over:,}" if carry_over > 0 else "定期月次"
            if persistent_note: notes_text += f"\n\n{persistent_note}"
            if cust_data.notes: notes_text += f"\n\n【特記事項】\n{cust_data.notes}"

            inv = models.Invoice(
                company_id=company_id,
                customer_id=cust_id,
                month=month,
                total_amount=grand_total,
                tax_amount=tax,
                status="draft",
                due_date=body.due_date or _auto_due_date(c, month),
                notes=notes_text,
            )
            db.add(inv)
            db.flush()

            for item in items:
                item.invoice_id = inv.id
                db.add(item)
                
            created.append(inv)

        db.commit()

        result = []
        for inv in created:
            loaded = db.query(models.Invoice).options(
                joinedload(models.Invoice.items),
                joinedload(models.Invoice.payments),
                joinedload(models.Invoice.customer),
            ).filter_by(id=inv.id).first()
            result.append(_invoice_to_out(loaded))

        return result

    except HTTPException:
        raise
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"一括生成に失敗しました: {str(e)}")


def _auto_due_date(customer, month: str) -> str | None:
    """業者の締め払い設定に基づいて支払期限日文字列を自動生成"""
    if not customer:
        return None
    import calendar
    try:
        inv_year, inv_month = int(month[:4]), int(month[5:7])
    except (ValueError, IndexError):
        return None
    offset = getattr(customer, 'payment_due_month_offset', 1) or 1
    due_day = getattr(customer, 'payment_due_day', 31) or 31
    pay_month = inv_month + offset
    pay_year = inv_year
    while pay_month > 12:
        pay_month -= 12
        pay_year += 1
    last_day = calendar.monthrange(pay_year, pay_month)[1]
    actual_due_day = min(due_day, last_day)
    return f"{pay_year}-{pay_month:02d}-{actual_due_day:02d}"


# ── 繰越処理 ──────────────────────────────────────────────
@router.post("/carryover", response_model=list[InvoiceOut])
def carryover_invoices(
    body: CarryoverRequest,
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
):
    """
    指定月の未入金請求書を検索し、差額を次月請求書に「前月繰越」として追加。
    繰越元の請求書ステータスを 'carried_over' に更新。
    """
    company_id = current_user.company_id

    # 繰越元月の未入金請求書を取得
    source_invoices = db.query(models.Invoice).options(
        joinedload(models.Invoice.items),
        joinedload(models.Invoice.payments),
        joinedload(models.Invoice.customer),
    ).filter(
        models.Invoice.company_id == company_id,
        models.Invoice.month == body.source_month,
        models.Invoice.status.in_(["sent", "partial", "overdue", "draft"]),
    ).all()

    # 重複排除
    seen = set()
    unique_sources = []
    for inv in source_invoices:
        if inv.id not in seen:
            seen.add(inv.id)
            unique_sources.append(inv)

    results = []
    for src in unique_sources:
        paid = sum(p.amount for p in src.payments)
        remaining = src.total_amount - paid
        if remaining <= 0:
            continue  # 完済済みはスキップ

        # 繰越先月の既存請求書を検索
        target_inv = db.query(models.Invoice).options(
            joinedload(models.Invoice.items),
            joinedload(models.Invoice.payments),
            joinedload(models.Invoice.customer),
        ).filter_by(
            company_id=company_id,
            customer_id=src.customer_id,
            month=body.target_month,
        ).first()

        if not target_inv:
            # 新しい請求書を作成
            target_inv = models.Invoice(
                company_id=company_id,
                customer_id=src.customer_id,
                month=body.target_month,
                status="draft",
                due_date=_auto_due_date(src.customer, body.target_month),
            )
            db.add(target_inv)
            db.flush()

        # 繰越の明細を追加
        carryover_item = models.InvoiceItem(
            invoice_id=target_inv.id,
            description=f"前月繰越 ({body.source_month})",
            quantity=1,
            unit="式",
            unit_price=remaining,
            amount=remaining,
        )
        db.add(carryover_item)

        # 繰越先の合計再計算
        existing_subtotal = sum(it.amount for it in target_inv.items) if target_inv.items else 0
        new_subtotal = existing_subtotal + remaining
        target_inv.tax_amount = int(new_subtotal * 0.1)
        target_inv.total_amount = new_subtotal + target_inv.tax_amount

        # 繰越元のステータスを更新
        src.status = "carried_over"
        src.notes = (src.notes or "") + f"\n※ {body.target_month}に繰越済 (残額¥{remaining:,})"

        results.append(target_inv)

    db.commit()

    # リロードして返す
    out = []
    for inv in results:
        loaded = db.query(models.Invoice).options(
            joinedload(models.Invoice.items),
            joinedload(models.Invoice.payments),
            joinedload(models.Invoice.customer),
        ).filter_by(id=inv.id).first()
        out.append(_invoice_to_out(loaded))

    return out


# ── 見積→請求書変換 ──────────────────────────────────────
@router.post("/from-estimate/{job_id}", response_model=InvoiceOut, status_code=201)
def create_invoice_from_estimate(
    job_id: str,
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
):
    """見積（案件）から直接請求書を生成。価格決まってる見積書はそのまま請求にする。"""
    job = db.query(models.Job).filter_by(
        job_id=job_id, company_id=current_user.company_id
    ).first()
    if not job:
        raise HTTPException(404, "案件が見つかりません")

    amount = job.final_price or job.estimated_price or job.price_total or 0
    if amount <= 0:
        raise HTTPException(400, "金額が0円です。見積金額を設定してください。")

    customer_id = job.customer_id
    if not customer_id:
        raise HTTPException(400, "案件に顧客が紐づいていません")

    customer = db.query(models.Customer).filter_by(id=customer_id).first()
    now = date.today()
    month = f"{now.year}-{now.month:02d}"

    due_date_str = _auto_due_date(customer, month)

    tax = int(amount * 0.1)
    inv = models.Invoice(
        company_id=current_user.company_id,
        customer_id=customer_id,
        month=month,
        total_amount=amount + tax,
        tax_amount=tax,
        status="draft",
        due_date=due_date_str,
        notes=f"案件「{job.job_name}」より変換",
    )
    db.add(inv)
    db.flush()

    db.add(models.InvoiceItem(
        invoice_id=inv.id,
        description=job.job_name or "業務委託",
        quantity=1,
        unit="式",
        unit_price=amount,
        amount=amount,
    ))

    if job.discount_amount and job.discount_amount > 0:
        db.add(models.InvoiceItem(
            invoice_id=inv.id,
            description="値引き",
            quantity=1,
            unit="式",
            unit_price=-job.discount_amount,
            amount=-job.discount_amount,
        ))

    if job.surcharge_amount and job.surcharge_amount > 0:
        db.add(models.InvoiceItem(
            invoice_id=inv.id,
            description="追加料金",
            quantity=1,
            unit="式",
            unit_price=job.surcharge_amount,
            amount=job.surcharge_amount,
        ))

    db.commit()
    db.refresh(inv)
    inv = db.query(models.Invoice).options(
        joinedload(models.Invoice.items),
        joinedload(models.Invoice.payments),
        joinedload(models.Invoice.customer),
    ).filter_by(id=inv.id).first()
    return _invoice_to_out(inv)


# ── 現場現金回収 (見積→請求→入金完了) ────────────────────────
@router.post("/cash-collection/{job_id}", response_model=InvoiceOut, status_code=201)
def record_cash_collection(
    job_id: str,
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
):
    """現場での現金回収: 見積から請求書を作り、即座に全額の現金入金履歴をつける"""
    job = db.query(models.Job).filter_by(
        job_id=job_id, company_id=current_user.company_id
    ).first()
    if not job:
        raise HTTPException(404, "案件が見つかりません")

    amount = job.final_price or job.estimated_price or job.price_total or 0
    if amount <= 0:
        raise HTTPException(400, "金額が0円です。見積金額を設定してください。")

    customer_id = job.customer_id
    if not customer_id:
        raise HTTPException(400, "案件に顧客が紐づいていません")

    customer = db.query(models.Customer).filter_by(id=customer_id).first()
    now = date.today()
    month = f"{now.year}-{now.month:02d}"
    due_date_str = _auto_due_date(customer, month)

    tax = int(amount * 0.1)
    total_with_tax = amount + tax

    inv = models.Invoice(
        company_id=current_user.company_id,
        customer_id=customer_id,
        month=month,
        total_amount=total_with_tax,
        tax_amount=tax,
        status="paid",  # 現金回収なのですぐにpaid
        due_date=due_date_str,
        notes=f"案件「{job.job_name}」より変換 (現場現金回収)",
    )
    db.add(inv)
    db.flush()

    db.add(models.InvoiceItem(
        invoice_id=inv.id,
        description=job.job_name or "業務委託",
        quantity=1,
        unit="式",
        unit_price=amount,
        amount=amount,
    ))

    if job.discount_amount and job.discount_amount > 0:
        db.add(models.InvoiceItem(
            invoice_id=inv.id,
            description="値引き",
            quantity=1,
            unit="式",
            unit_price=-job.discount_amount,
            amount=-job.discount_amount,
        ))

    if job.surcharge_amount and job.surcharge_amount > 0:
        db.add(models.InvoiceItem(
            invoice_id=inv.id,
            description="追加料金",
            quantity=1,
            unit="式",
            unit_price=job.surcharge_amount,
            amount=job.surcharge_amount,
        ))

    db.flush()

    # 現金入金履歴の追加
    db.add(models.Payment(
        invoice_id=inv.id,
        company_id=current_user.company_id,
        amount=total_with_tax,
        payment_date=now.isoformat(),
        payment_method="cash",
        notes="現場現金回収"
    ))

    # 案件のステータスを自動更新（任意）
    job.stage = "completed"

    db.commit()
    db.refresh(inv)
    inv = db.query(models.Invoice).options(
        joinedload(models.Invoice.items),
        joinedload(models.Invoice.payments),
        joinedload(models.Invoice.customer),
    ).filter_by(id=inv.id).first()
    return _invoice_to_out(inv)


class SendInvoiceRequest(BaseModel):
    subject: str = "【ご請求書】送付のご案内"
    body: str = "いつも大変お世話になっております。\n添付の通り、ご請求書を送付いたします。\nご確認のほどよろしくお願い申し上げます。"


@router.get("/{invoice_id}/pdf")
async def get_invoice_pdf(
    invoice_id: str,
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
):
    inv = db.query(models.Invoice).options(
        joinedload(models.Invoice.items),
        joinedload(models.Invoice.payments),
        joinedload(models.Invoice.customer),
    ).filter_by(id=invoice_id, company_id=current_user.company_id).first()
    if not inv:
        raise HTTPException(404, "請求書が見つかりません")
    company = db.query(models.Company).filter_by(id=current_user.company_id).first()
    settings = db.query(models.CompanySettings).filter_by(company_id=current_user.company_id).first()

    # Jinja2 render
    env = Environment(loader=FileSystemLoader(os.path.join(os.path.dirname(__file__), "..", "templates")))
    template = env.get_template("invoice.html")
    html_content = template.render(
        invoice=inv,
        customer=inv.customer,
        company=company,
        settings=settings,
        today=datetime.now().strftime("%Y年%m月%d日")
    )

    # WeasyPrint PDF generation
    template_dir = os.path.join(os.path.dirname(__file__), "..", "templates")
    try:
        pdf_bytes = weasyprint.HTML(string=html_content, base_url=template_dir).write_pdf()
    except Exception as e:
        print("WeasyPrint PDF generation failed:", e)
        raise HTTPException(500, f"PDF生成に失敗しました: {e}")

    return Response(content=pdf_bytes, media_type="application/pdf")

@router.post("/{invoice_id}/send", response_model=InvoiceOut)
async def send_invoice_email(
    invoice_id: str,
    body: SendInvoiceRequest,
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
):
    try:
        inv = db.query(models.Invoice).options(
            joinedload(models.Invoice.items),
            joinedload(models.Invoice.payments),
            joinedload(models.Invoice.customer),
        ).filter_by(id=invoice_id, company_id=current_user.company_id).first()

        if not inv:
            raise HTTPException(404, "請求書が見つかりません")
        if not inv.customer or not inv.customer.email:
            raise HTTPException(400, "顧客のメールアドレスが登録されていません")

        company = db.query(models.Company).filter_by(id=current_user.company_id).first()
        settings = db.query(models.CompanySettings).filter_by(company_id=current_user.company_id).first()

        # Generate PDF in memory
        env = Environment(loader=FileSystemLoader(os.path.join(os.path.dirname(__file__), "..", "templates")))
        template = env.get_template("invoice.html")
        html_content = template.render(
            invoice=inv,
            customer=inv.customer,
            company=company,
            settings=settings,
            today=datetime.now().strftime("%Y年%m月%d日")
        )
        
        # WeasyPrint PDF generation for email attachment
        template_dir = os.path.join(os.path.dirname(__file__), "..", "templates")
        pdf_bytes = None
        try:
            pdf_bytes = weasyprint.HTML(string=html_content, base_url=template_dir).write_pdf()
        except Exception as e:
            print("WeasyPrint PDF generation failed for email:", e)
            raise HTTPException(500, f"PDF生成に失敗しました: {e}")

        # Email properties
        # Email properties derived from database settings rather than env variables
        smtp_host = settings.smtp_host if settings and settings.smtp_host else os.getenv("SMTP_HOST", "smtp.ocn.ne.jp")
        smtp_port = settings.smtp_port if settings and settings.smtp_port else int(os.getenv("SMTP_PORT", "587"))
        smtp_user = settings.smtp_user if settings and settings.smtp_user else os.getenv("SMTP_USER", "")
        smtp_pass = settings.smtp_password if settings and settings.smtp_password else os.getenv("SMTP_PASS", "")

        if not smtp_user or not smtp_pass:
            raise HTTPException(400, "SMTP設定（メールサーバーのユーザー名・パスワード）が未設定です。設定画面から登録してください。")

        from_email = smtp_user
        if "amazonaws.com" in smtp_host:
            from_email = "info@yamabun-ryubee.jp"

        msg = MIMEMultipart()
        msg['From'] = formataddr((str(Header(company.name, 'utf-8')), from_email))
        msg['To'] = inv.customer.email
        msg['Subject'] = body.subject
        body_text = body.body.replace('\\n', '\n')
        msg.attach(MIMEText(body_text, 'plain'))

        # PDF添付
        part = MIMEBase('application', 'pdf')
        part.set_payload(pdf_bytes)
        encoders.encode_base64(part)
        filename = f"Invoice_{inv.month}_{inv.customer.name}.pdf".replace(" ", "_")
        part.add_header('Content-Disposition', 'attachment', filename=filename)
        msg.attach(part)

        try:
            if smtp_port == 465:
                server = smtplib.SMTP_SSL(smtp_host, smtp_port, timeout=15)
            else:
                server = smtplib.SMTP(smtp_host, smtp_port, timeout=15)
                server.starttls()
            server.login(smtp_user, smtp_pass)
            server.send_message(msg)
            server.quit()
        except Exception as e:
            raise HTTPException(500, f"メール送信に失敗しました: {e}")

        inv.sent_at = datetime.now().isoformat(timespec='seconds')
        db.commit()
        db.refresh(inv)
        return _invoice_to_out(inv)

    except HTTPException:
        raise
    except Exception as e:
        import traceback
        err_msg = traceback.format_exc()
        print(f"Unhandled Exception in send_invoice_email: {err_msg}")
        raise HTTPException(status_code=500, detail=f"内部エラーにより送信失敗しました: {str(e)}")


class SendRemindersResponse(BaseModel):
    sent_count: int
    logs: list[str]

@router.post("/send-reminders", response_model=SendRemindersResponse)
def send_reminders(
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
):
    """
    未入金アラートが出ている顧客（かつメールアドレスがある）に一斉にリマインドを送信する。
    ※今回は実際のSMTP送信ではなく、ログに出力して last_reminded_at を更新する。
    """
    # 1. 会社設定（テンプレート）を取得
    settings = db.query(models.CompanySettings).filter_by(
        company_id=current_user.company_id
    ).first()
    company = db.query(models.Company).filter_by(id=current_user.company_id).first()
    
    subject_tmpl = settings.unpaid_email_subject if settings else "【重要】未入金のお知らせ"
    body_tmpl = settings.unpaid_email_body if settings else "未入金のお知らせ\n\n{{customer_name}}様\n請求月: {{month}}\n金額: ¥{{amount}}\n期限: {{due_date}}"

    # 2. 未入金アラートリストを取得（再利用）
    alerts = unpaid_alerts(current_user=current_user, db=db)
    
    sent_count = 0
    logs = []
    now_str = datetime.now().isoformat(timespec='seconds')

    for alert in alerts:
        if not alert.email:
            continue
            
        # Invoice取得して最新状態確認
        inv = db.query(models.Invoice).filter_by(id=alert.invoice_id).first()
        if not inv:
            continue
            
        # 生成
        body = body_tmpl.replace("{{customer_name}}", alert.customer_name)
        body = body.replace("{{month}}", alert.month)
        body = body.replace("{{amount}}", f"{alert.remaining:,}")
        due_str = alert.due_date or "指定なし"
        body = body.replace("{{due_date}}", due_str)
        
        smtp_host = settings.smtp_host if settings and settings.smtp_host else os.getenv("SMTP_HOST", "smtp.ocn.ne.jp")
        smtp_port = settings.smtp_port if settings and settings.smtp_port else int(os.getenv("SMTP_PORT", "587"))
        smtp_user = settings.smtp_user if settings and settings.smtp_user else os.getenv("SMTP_USER", "")
        smtp_pass = settings.smtp_password if settings and settings.smtp_password else os.getenv("SMTP_PASS", "")

        if smtp_user and smtp_pass:
            from_email = smtp_user
            if "amazonaws.com" in smtp_host:
                from_email = "info@yamabun-ryubee.jp"

            try:
                msg = MIMEMultipart()
                msg['From'] = formataddr((str(Header(company.name, 'utf-8')), from_email))
                msg['To'] = alert.email
                msg['Subject'] = subject_tmpl
                msg.attach(MIMEText(body, 'plain'))
                
                if smtp_port == 465:
                    server = smtplib.SMTP_SSL(smtp_host, smtp_port, timeout=15)
                else:
                    server = smtplib.SMTP(smtp_host, smtp_port, timeout=15)
                    server.starttls()
                server.login(smtp_user, smtp_pass)
                server.send_message(msg)
                server.quit()
                logs.append(f"Sent successfully to {alert.email} ({alert.customer_name})")
            except Exception as e:
                logs.append(f"Failed to send to {alert.email} ({alert.customer_name}): {e}")
        else:
            # 本来ならここで send_email(to=alert.email, subject=subject_tmpl, body=body) を実行する
            logs.append(f"SMTP not configued. Failed to send to {alert.email} ({alert.customer_name}): ¥{alert.remaining:,}")
        
        # 記録更新
        inv.last_reminded_at = now_str
        sent_count += 1

    db.commit()
    return SendRemindersResponse(sent_count=sent_count, logs=logs)
