"""口座振替ルーター: 全銀フォーマットCSV生成・振替結果取込"""
import csv
import io
import uuid
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session, joinedload
from app.database import get_db
from app import models, auth

router = APIRouter(prefix="/v1/auto-debit", tags=["auto-debit"])


# ── Schemas ────────────────────────────────────────────
class DebitGenerateRequest(BaseModel):
    invoice_ids: list[str]
    debit_date: str  # 振替日 YYYY-MM-DD
    consignor_code: str = "0000000000"  # 委託者コード (10桁)
    consignor_name: str = "ﾔﾏﾌﾞﾝ"  # 委託者名 (カナ)
    bank_code: str = "0158"  # 引落銀行コード (京都銀行=0158)
    branch_code: str = "001"  # 引落支店コード


class DebitResultItem(BaseModel):
    invoice_id: str
    customer_name: str
    amount: int
    status: str  # success / failed
    failure_reason: str = ""


# ── 全銀フォーマットCSV生成 ──────────────────────────────
@router.post("/generate")
def generate_debit_csv(
    body: DebitGenerateRequest,
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
):
    """
    チェックされた請求書から全銀フォーマット（固定長テキスト）の口座振替データを生成。
    実用的にはCSV形式で出力（京都銀行の振替依頼データ形式）。
    """
    company_id = current_user.company_id

    invoices = db.query(models.Invoice).options(
        joinedload(models.Invoice.customer),
        joinedload(models.Invoice.payments),
    ).filter(
        models.Invoice.id.in_(body.invoice_ids),
        models.Invoice.company_id == company_id,
    ).all()

    if not invoices:
        raise HTTPException(400, "対象の請求書がありません")

    # CSV生成
    output = io.StringIO()
    writer = csv.writer(output)

    # ヘッダー行
    writer.writerow([
        "振替日", "銀行コード", "支店コード", "預金種目",
        "口座番号", "口座名義", "振替金額", "顧客名", "請求書ID"
    ])

    skipped = []
    generated = []

    for inv in invoices:
        cust = inv.customer
        if not cust:
            skipped.append({"invoice_id": inv.id, "reason": "顧客なし"})
            continue

        # 口座情報の確認
        if not cust.bank_code or not cust.branch_code or not cust.account_number:
            skipped.append({"invoice_id": inv.id, "reason": f"{cust.name}: 口座情報未登録"})
            continue

        # 既に入金済みの差額のみ振替
        paid = sum(p.amount for p in inv.payments)
        remaining = inv.total_amount - paid
        if remaining <= 0:
            skipped.append({"invoice_id": inv.id, "reason": f"{cust.name}: 入金済み"})
            continue

        writer.writerow([
            body.debit_date,
            cust.bank_code.ljust(4, "0"),
            cust.branch_code.ljust(3, "0"),
            cust.account_type or "1",  # 1=普通
            cust.account_number.ljust(7, "0"),
            (cust.account_holder or cust.name)[:30],
            remaining,
            cust.name,
            inv.id,
        ])
        generated.append(inv.id)

    csv_content = output.getvalue()
    output.close()

    if not generated:
        return {"generated": 0, "skipped": skipped, "message": "振替対象なし"}

    # CSVをレスポンスとして返す
    csv_bytes = csv_content.encode("shift_jis", errors="replace")
    return StreamingResponse(
        io.BytesIO(csv_bytes),
        media_type="text/csv",
        headers={
            "Content-Disposition": f'attachment; filename="auto_debit_{body.debit_date}.csv"',
            "X-Generated-Count": str(len(generated)),
            "X-Skipped-Count": str(len(skipped)),
        },
    )


# ── 対象請求書プレビュー ──────────────────────────────────
@router.get("/preview")
def preview_debit_targets(
    month: str = Query(...),
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
):
    """指定月の口座振替対象となる未払い請求書を一覧"""
    invoices = db.query(models.Invoice).options(
        joinedload(models.Invoice.customer),
        joinedload(models.Invoice.payments),
    ).filter(
        models.Invoice.company_id == current_user.company_id,
        models.Invoice.month == month,
        models.Invoice.status.in_(["sent", "partial", "overdue", "draft"]),
    ).all()

    seen = set()
    results = []
    for inv in seen_filter(invoices, seen):
        cust = inv.customer
        paid = sum(p.amount for p in inv.payments)
        remaining = inv.total_amount - paid
        if remaining <= 0:
            continue

        has_bank = bool(cust and cust.bank_code and cust.branch_code and cust.account_number)
        results.append({
            "invoice_id": inv.id,
            "customer_id": inv.customer_id,
            "customer_name": cust.name if cust else "",
            "month": inv.month,
            "total_amount": inv.total_amount,
            "paid_total": paid,
            "remaining": remaining,
            "has_bank_info": has_bank,
            "bank_code": cust.bank_code if cust else "",
            "account_holder": cust.account_holder if cust else "",
        })

    return results


def seen_filter(items, seen):
    for item in items:
        if item.id not in seen:
            seen.add(item.id)
            yield item


# ── 振替結果取込 ──────────────────────────────────────────
FAILURE_REASONS = {
    "1": "残高不足",
    "2": "取引なし",
    "3": "預金者停止",
    "4": "依頼書無し",
    "8": "委託者停止",
    "9": "その他",
}

# コード1(残高不足)以外は即時アラート。コード1は2回連続でアラート。
IMMEDIATE_ALERT_CODES = {"2", "3", "4", "8", "9"}


@router.post("/import-result")
async def import_debit_result(
    file: UploadFile = File(...),
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
):
    """
    口座振替結果CSVを取り込み、成功分は自動入金処理、不能分は理由付きで返す。
    CSV形式: 振替日, 銀行コード, 支店コード, 口座番号, 口座名義, 振替金額, 結果コード(0=成功), 不能理由コード
    
    アラートルール:
    - コード1(残高不足): 2回連続で発生した場合のみアラート
    - コード2,3,4,8: 即時アラート
    """
    content = await file.read()
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError:
        try:
            text = content.decode("shift_jis")
        except UnicodeDecodeError:
            text = content.decode("cp932")

    reader = csv.reader(io.StringIO(text))
    company_id = current_user.company_id

    success_count = 0
    failed_items = []
    alerts = []

    # ヘッダーをスキップ
    header = next(reader, None)

    for row in reader:
        if len(row) < 7:
            continue

        debit_date = row[0].strip()
        account_number = row[3].strip()
        amount_str = row[5].strip().replace(",", "").replace("¥", "")
        result_code = row[6].strip()  # 0=成功
        failure_code = row[7].strip() if len(row) > 7 else ""

        try:
            amount = int(amount_str)
        except ValueError:
            continue

        # 口座番号で顧客を特定
        customer = db.query(models.Customer).filter(
            models.Customer.company_id == company_id,
            models.Customer.account_number == account_number,
        ).first()

        if result_code == "0":
            # 成功 → 入金処理 + 連続残高不足カウンタをリセット
            if customer:
                unpaid = db.query(models.Invoice).filter(
                    models.Invoice.company_id == company_id,
                    models.Invoice.customer_id == customer.id,
                    models.Invoice.status.in_(["sent", "partial", "overdue", "draft"]),
                ).order_by(models.Invoice.month.asc()).first()

                if unpaid:
                    payment = models.Payment(
                        invoice_id=unpaid.id,
                        company_id=company_id,
                        amount=amount,
                        payment_date=debit_date,
                        payment_method="auto_debit",
                        notes="口座振替による自動入金",
                    )
                    db.add(payment)

                    total_paid = sum(p.amount for p in unpaid.payments) + amount
                    if total_paid >= unpaid.total_amount:
                        unpaid.status = "paid"
                    else:
                        unpaid.status = "partial"

                    success_count += 1

                # 成功したら連続残高不足カウンタをリセット
                _update_consecutive_failure(db, customer, 0)
        else:
            # 不能 → 結果を返す
            reason = FAILURE_REASONS.get(failure_code, f"不明 (コード:{failure_code})")
            cust_name = customer.name if customer else "不明"

            failed_item = {
                "account_number": account_number,
                "customer_id": customer.id if customer else None,
                "customer_name": cust_name,
                "amount": amount,
                "failure_code": failure_code,
                "failure_reason": reason,
                "alert": False,
                "alert_message": "",
            }

            if failure_code in IMMEDIATE_ALERT_CODES:
                # コード2,3,4,8 → 即時アラート
                failed_item["alert"] = True
                failed_item["alert_message"] = f"⚠️ {cust_name}: {reason} — 要確認"
                if customer:
                    _update_consecutive_failure(db, customer, 0)  # 残高不足カウンタはリセット
            elif failure_code == "1":
                # コード1(残高不足) → 連続カウント
                if customer:
                    prev_count = _get_consecutive_failure(customer)
                    new_count = prev_count + 1
                    _update_consecutive_failure(db, customer, new_count)

                    if new_count >= 2:
                        failed_item["alert"] = True
                        failed_item["alert_message"] = f"🔴 {cust_name}: 残高不足が{new_count}回連続 — 要対応"
                    else:
                        failed_item["alert_message"] = f"残高不足 (1回目 — 次回も不能の場合アラート)"

            failed_items.append(failed_item)
            if failed_item["alert"]:
                alerts.append(failed_item)

    db.commit()
    return {
        "success_count": success_count,
        "failed_count": len(failed_items),
        "failed_items": failed_items,
        "alerts": alerts,
        "alert_count": len(alerts),
    }


def _get_consecutive_failure(customer) -> int:
    """顧客のform_dataから連続残高不足カウントを取得"""
    import json
    try:
        fd = json.loads(customer.form_data or "{}")
        return int(fd.get("consecutive_debit_failure", 0))
    except (json.JSONDecodeError, ValueError):
        return 0


def _update_consecutive_failure(db, customer, count: int):
    """顧客のform_dataに連続残高不足カウントを保存"""
    import json
    if not customer:
        return
    try:
        fd = json.loads(customer.form_data or "{}")
    except json.JSONDecodeError:
        fd = {}
    fd["consecutive_debit_failure"] = count
    customer.form_data = json.dumps(fd, ensure_ascii=False)

