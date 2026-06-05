"""入金・消し込みルーター"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session, joinedload
from app.database import get_db
from app import models, auth

router = APIRouter(prefix="/v1/payments", tags=["payments"])


class PaymentCreate(BaseModel):
    invoice_id: str
    amount: int
    payment_date: str
    payment_method: str = "bank_transfer"  # bank_transfer / cash / other
    notes: str = ""
    fee_amount: int = 0          # M-2: 手数料・協力会費の差引額
    fee_reason: str = ""         # M-2: 差額理由（振込手数料/協力会費/その他）


class PaymentOut(BaseModel):
    id: str
    invoice_id: str
    company_id: str
    amount: int
    payment_date: str
    payment_method: str
    notes: str
    created_at: str
    # 請求書の情報も返す
    invoice_month: str = ""
    invoice_total: int = 0
    invoice_status: str = ""
    customer_name: str = ""

    model_config = {"from_attributes": True}


@router.get("", response_model=list[PaymentOut])
def list_payments(
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
):
    payments = db.query(models.Payment).filter_by(
        company_id=current_user.company_id
    ).order_by(models.Payment.created_at.desc()).all()
    return [_payment_to_out(p, db) for p in payments]


@router.post("", response_model=PaymentOut, status_code=201)
def create_payment(
    body: PaymentCreate,
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
):
    """入金登録 & 自動消し込み（請求書ステータス更新）"""
    inv = db.query(models.Invoice).filter_by(
        id=body.invoice_id, company_id=current_user.company_id
    ).first()
    if not inv:
        raise HTTPException(404, "請求書が見つかりません")

    # M-2: 手数料差引きの場合、備考に理由を記録
    notes = body.notes
    if body.fee_amount > 0 and body.fee_reason:
        notes = f"[{body.fee_reason}: ¥{body.fee_amount:,}差引] {notes}".strip()

    payment = models.Payment(
        invoice_id=body.invoice_id,
        company_id=current_user.company_id,
        amount=body.amount,
        payment_date=body.payment_date,
        payment_method=body.payment_method,
        notes=notes,
    )
    db.add(payment)
    db.flush()

    # 消し込み: 入金合計(+手数料差引) vs 請求額
    total_paid = sum(
        p.amount for p in
        db.query(models.Payment).filter_by(invoice_id=inv.id).all()
    )
    effective_paid = total_paid + body.fee_amount  # 手数料も「支払済み」として扱う
    if effective_paid >= inv.total_amount:
        inv.status = "paid"
    elif total_paid > 0:
        inv.status = "partial"

    db.commit()
    db.refresh(payment)
    return _payment_to_out(payment, db)


@router.delete("/{payment_id}", status_code=204)
def delete_payment(
    payment_id: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.require_admin),
):
    """入金取消 & 請求書ステータスの再計算"""
    payment = db.query(models.Payment).filter_by(
        id=payment_id, company_id=current_user.company_id
    ).first()
    if not payment:
        raise HTTPException(404, "入金記録が見つかりません")

    inv_id = payment.invoice_id
    db.delete(payment)
    db.flush()

    # 残りの入金額で再計算
    inv = db.query(models.Invoice).filter_by(id=inv_id).first()
    if inv:
        remaining_paid = sum(
            p.amount for p in
            db.query(models.Payment).filter_by(invoice_id=inv_id).all()
        )
        if remaining_paid >= inv.total_amount:
            inv.status = "paid"
        elif remaining_paid > 0:
            inv.status = "partial"
        else:
            inv.status = "sent" if inv.sent_at else "draft"

    db.commit()


# ── M-2: 複数請求書への一括振り分け入金 ──
class BulkAllocation(BaseModel):
    invoice_id: str
    amount: int

class BulkPaymentCreate(BaseModel):
    allocations: list[BulkAllocation]
    payment_date: str
    payment_method: str = "bank_transfer"
    notes: str = ""
    fee_amount: int = 0
    fee_reason: str = ""

class BulkPaymentResponse(BaseModel):
    created: int
    total_allocated: int

@router.post("/bulk-allocate", response_model=BulkPaymentResponse, status_code=201)
def bulk_allocate_payment(
    body: BulkPaymentCreate,
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
):
    """
    1回の振込を複数の請求書に振り分けて入金登録。
    管理会社のまとめ払いや数ヶ月分一括振込に対応。
    """
    if not body.allocations:
        raise HTTPException(400, "振り分け先を1件以上指定してください")

    company_id = current_user.company_id
    notes_base = body.notes
    if body.fee_amount > 0 and body.fee_reason:
        notes_base = f"[{body.fee_reason}: ¥{body.fee_amount:,}差引] {notes_base}".strip()

    total_allocated = 0
    created = 0

    for alloc in body.allocations:
        inv = db.query(models.Invoice).filter_by(
            id=alloc.invoice_id, company_id=company_id
        ).first()
        if not inv:
            continue

        payment = models.Payment(
            invoice_id=alloc.invoice_id,
            company_id=company_id,
            amount=alloc.amount,
            payment_date=body.payment_date,
            payment_method=body.payment_method,
            notes=f"[一括振分] {notes_base}".strip() if len(body.allocations) > 1 else notes_base,
        )
        db.add(payment)
        db.flush()

        # ステータス更新
        total_paid = sum(
            p.amount for p in
            db.query(models.Payment).filter_by(invoice_id=inv.id).all()
        )
        if total_paid >= inv.total_amount:
            inv.status = "paid"
        elif total_paid > 0:
            inv.status = "partial"

        total_allocated += alloc.amount
        created += 1

    db.commit()
    return BulkPaymentResponse(created=created, total_allocated=total_allocated)


# ── M-2: 差額承認（手数料差引きで完了扱い）──
class SettleDifferenceRequest(BaseModel):
    invoice_id: str
    fee_amount: int          # 手数料・値引き等の差額
    fee_reason: str = "振込手数料"  # 理由
    notes: str = ""

@router.post("/settle-difference", status_code=200)
def settle_with_difference(
    body: SettleDifferenceRequest,
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
):
    """
    入金済みだが差額がある請求書を、差額理由を記録して完了扱いにする。
    手数料差引き、協力会費差引き等に使用。
    """
    inv = db.query(models.Invoice).filter_by(
        id=body.invoice_id, company_id=current_user.company_id
    ).first()
    if not inv:
        raise HTTPException(404, "請求書が見つかりません")

    total_paid = sum(
        p.amount for p in
        db.query(models.Payment).filter_by(invoice_id=inv.id).all()
    )
    remaining = inv.total_amount - total_paid

    if body.fee_amount < remaining:
        raise HTTPException(400, f"差額 ¥{remaining:,} に対して承認額 ¥{body.fee_amount:,} が不足しています")

    # 差額分を「手数料入金」として記録（実際の金銭移動なし）
    adj_payment = models.Payment(
        invoice_id=body.invoice_id,
        company_id=current_user.company_id,
        amount=remaining,
        payment_date=body.notes or "差額承認",
        payment_method="adjustment",
        notes=f"[差額承認: {body.fee_reason}] 差額¥{remaining:,}を承認",
    )
    db.add(adj_payment)
    inv.status = "paid"
    db.commit()

    return {"message": f"差額 ¥{remaining:,} を「{body.fee_reason}」として承認し、完了にしました"}


def _payment_to_out(p: models.Payment, db: Session) -> PaymentOut:
    inv = db.query(models.Invoice).options(
        joinedload(models.Invoice.customer)
    ).filter_by(id=p.invoice_id).first()
    return PaymentOut(
        id=p.id,
        invoice_id=p.invoice_id,
        company_id=p.company_id,
        amount=p.amount,
        payment_date=p.payment_date,
        payment_method=p.payment_method,
        notes=p.notes,
        created_at=p.created_at.isoformat(),
        invoice_month=inv.month if inv else "",
        invoice_total=inv.total_amount if inv else 0,
        invoice_status=inv.status if inv else "",
        customer_name=inv.customer.name if inv and inv.customer else "",
    )

