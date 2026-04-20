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

    payment = models.Payment(
        invoice_id=body.invoice_id,
        company_id=current_user.company_id,
        amount=body.amount,
        payment_date=body.payment_date,
        payment_method=body.payment_method,
        notes=body.notes,
    )
    db.add(payment)
    db.flush()

    # 消し込み: 入金合計 vs 請求額
    total_paid = sum(
        p.amount for p in
        db.query(models.Payment).filter_by(invoice_id=inv.id).all()
    )
    if total_paid >= inv.total_amount:
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
