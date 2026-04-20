"""銀行入金取込ルーター: CSVアップロード・自動マッチング・消し込み"""
import csv
import io
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import func
from app.database import get_db
from app import models, auth

router = APIRouter(prefix="/v1/bank", tags=["bank"])


# ── Schemas ────────────────────────────────────────────
class MatchResult(BaseModel):
    transaction_id: str
    payer_name: str
    amount: int
    status: str
    matched_customer_name: str | None = None
    matched_invoice_id: str | None = None


# ── CSV Upload ─────────────────────────────────────────
@router.post("/upload")
async def upload_bank_csv(
    file: UploadFile = File(...),
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
):
    """
    京都銀行CSVをアップロードして入金データを取り込む
    対応フォーマット: 日付, 振込人名義, 入金額 (カンマ区切り)
    """
    content = await file.read()
    # Shift-JIS or UTF-8
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = content.decode("shift_jis")

    reader = csv.reader(io.StringIO(text))
    imported = 0

    for row in reader:
        if len(row) < 3:
            continue
        # ヘッダー行スキップ
        date_str = row[0].strip()
        if not date_str or not date_str[0].isdigit():
            continue

        payer = row[1].strip()
        try:
            amount = int(row[2].strip().replace(",", "").replace("¥", ""))
        except ValueError:
            continue

        if amount <= 0:
            continue

        txn = models.BankTransaction(
            company_id=current_user.company_id,
            transaction_date=date_str,
            amount=amount,
            payer_name=payer,
            payer_name_kana=payer,  # CSVが全角カナの場合そのまま使用
            status="unmatched",
        )
        db.add(txn)
        imported += 1

    db.commit()
    return {"imported": imported}


# ── 自動マッチング ──────────────────────────────────────
@router.post("/auto-match")
def auto_match(
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
):
    """
    未マッチの銀行入金を顧客名で自動マッチング → 対応する未払い請求書に消し込み
    """
    unmatched = (
        db.query(models.BankTransaction)
        .filter_by(company_id=current_user.company_id, status="unmatched")
        .all()
    )

    customers = db.query(models.Customer).filter_by(company_id=current_user.company_id).all()
    cust_map = {}
    for c in customers:
        # 名前の部分一致マッチング（カナ・漢字両方）
        cust_map[c.name.strip()] = c
        if c.contact_person:
            cust_map[c.contact_person.strip()] = c

    matched_count = 0
    results = []

    for txn in unmatched:
        matched_customer = None
        # 振込人名義で顧客を検索（部分一致）
        for name_key, customer in cust_map.items():
            if name_key and (name_key in txn.payer_name or txn.payer_name in name_key):
                matched_customer = customer
                break

        if matched_customer:
            txn.matched_customer_id = matched_customer.id

            # この顧客の未払い請求書を検索（金額一致 or 最も古いもの）
            unpaid_invoice = (
                db.query(models.Invoice)
                .filter(
                    models.Invoice.company_id == current_user.company_id,
                    models.Invoice.customer_id == matched_customer.id,
                    models.Invoice.status.in_(["sent", "partial", "overdue"]),
                )
                .order_by(models.Invoice.month.asc())
                .first()
            )

            if unpaid_invoice:
                txn.matched_invoice_id = unpaid_invoice.id
                txn.status = "matched"

                # 入金レコードを作成
                payment = models.Payment(
                    invoice_id=unpaid_invoice.id,
                    company_id=current_user.company_id,
                    amount=txn.amount,
                    payment_date=txn.transaction_date,
                    payment_method="bank_transfer",
                    notes=f"京都銀行自動消込 ({txn.payer_name})",
                )
                db.add(payment)

                # 請求書ステータス更新
                total_paid = sum(p.amount for p in unpaid_invoice.payments) + txn.amount
                if total_paid >= unpaid_invoice.total_amount:
                    unpaid_invoice.status = "paid"
                    txn.status = "reconciled"
                else:
                    unpaid_invoice.status = "partial"

                matched_count += 1

            results.append(MatchResult(
                transaction_id=txn.id,
                payer_name=txn.payer_name,
                amount=txn.amount,
                status=txn.status,
                matched_customer_name=matched_customer.name,
                matched_invoice_id=txn.matched_invoice_id,
            ))
        else:
            results.append(MatchResult(
                transaction_id=txn.id,
                payer_name=txn.payer_name,
                amount=txn.amount,
                status="unmatched",
            ))

    db.commit()
    return {"matched": matched_count, "total": len(unmatched), "results": [r.model_dump() for r in results]}


# ── 未マッチ一覧 ────────────────────────────────────────
@router.get("/unmatched")
def get_unmatched(
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
):
    txns = (
        db.query(models.BankTransaction)
        .filter_by(company_id=current_user.company_id, status="unmatched")
        .order_by(models.BankTransaction.transaction_date.desc())
        .all()
    )
    return [
        {
            "id": t.id,
            "transaction_date": t.transaction_date,
            "amount": t.amount,
            "payer_name": t.payer_name,
            "status": t.status,
        }
        for t in txns
    ]


# ── 全入金履歴 ──────────────────────────────────────────
@router.get("/transactions")
def get_transactions(
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
):
    txns = (
        db.query(models.BankTransaction)
        .filter_by(company_id=current_user.company_id)
        .order_by(models.BankTransaction.transaction_date.desc())
        .limit(100)
        .all()
    )
    return [
        {
            "id": t.id,
            "transaction_date": t.transaction_date,
            "amount": t.amount,
            "payer_name": t.payer_name,
            "status": t.status,
            "matched_customer_id": t.matched_customer_id,
            "matched_invoice_id": t.matched_invoice_id,
        }
        for t in txns
    ]
