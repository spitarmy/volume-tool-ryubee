"""銀行入金取込ルーター: CSVアップロード・自動マッチング・消し込み"""
import csv
import io
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from pydantic import BaseModel
from sqlalchemy.orm import Session, joinedload
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
    # ニアピン候補
    near_matches: list[dict] | None = None


class ManualMatchRequest(BaseModel):
    transaction_id: str
    invoice_id: str


# ── CSV Upload ─────────────────────────────────────────
@router.post("/upload")
async def upload_bank_csv(
    file: UploadFile = File(...),
    bank_type: str = Form("kyoto"),
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
):
    """
    銀行CSVをアップロードして入金データを取り込む
    対応フォーマット: 日付, 振込人名義, 入金額 (カンマ区切り)
    重複取込防止: 同じ日付・名義・金額の組み合わせがあればスキップ
    """
    content = await file.read()
    # Shift-JIS or UTF-8
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = content.decode("shift_jis")

    reader = csv.reader(io.StringIO(text))
    imported = 0
    skipped = 0

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

        # ★ FIX 1: 重複取込防止 ─ 同じ日付・名義・金額の組み合わせがあればスキップ
        existing = (
            db.query(models.BankTransaction)
            .filter_by(
                company_id=current_user.company_id,
                transaction_date=date_str,
                payer_name=payer,
                amount=amount,
            )
            .first()
        )
        if existing:
            skipped += 1
            continue

        bank_name_str = "京都中央信用金庫" if bank_type == "kyoto_chuo" else "京都銀行"
        txn = models.BankTransaction(
            company_id=current_user.company_id,
            transaction_date=date_str,
            amount=amount,
            payer_name=payer,
            payer_name_kana=payer,  # CSVが全角カナの場合そのまま使用
            bank_name=bank_name_str,
            status="unmatched",
        )
        db.add(txn)
        imported += 1

    db.commit()
    return {"imported": imported, "skipped": skipped}


# ── 自動マッチング ──────────────────────────────────────
@router.post("/auto-match")
def auto_match(
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
):
    """
    未マッチの銀行入金を顧客名で自動マッチング → 対応する未払い請求書に消し込み
    名前が一致しなくても金額が一致する請求書があれば「ニアピン候補」として返す
    """
    unmatched = (
        db.query(models.BankTransaction)
        .filter_by(company_id=current_user.company_id, status="unmatched")
        .all()
    )

    customers = db.query(models.Customer).filter_by(company_id=current_user.company_id).all()

    # ── 名前正規化: 法人格や記号を除去して「核」の名前を抽出 ──
    import re

    # 除去する法人格・記号パターン（漢字・カナ両方）
    STRIP_PATTERNS = [
        # 漢字法人格
        r'株式会社', r'有限会社', r'合同会社', r'合資会社', r'合名会社',
        r'一般社団法人', r'一般財団法人', r'社会福祉法人', r'医療法人',
        r'特定非営利活動法人', r'NPO法人',
        # 略称（括弧付き）
        r'\(株\)', r'（株）', r'\(有\)', r'（有）', r'\(合\)', r'（合）',
        # カナ法人格（銀行CSVでよく使われる）
        r'カ\)', r'カ）', r'\(カ', r'（カ', r'ユ\)', r'ユ）', r'\(ユ', r'（ユ',
        r'ド\)', r'ド）', r'\(ド', r'（ド',
        # 一般的な接尾語
        r'御中', r'様',
    ]

    def normalize_name(name: str) -> str:
        """法人格・記号を除去し、核となる名前を抽出する"""
        s = name.strip()
        for pat in STRIP_PATTERNS:
            s = re.sub(pat, '', s)
        # 全角・半角スペース、記号を除去
        s = re.sub(r'[\s　・\-\.\(\)（）「」\u3000]+', '', s)
        return s.strip()

    # 顧客名マップ: { 正規化名: customer } と { 元の名前: customer }
    cust_entries = []  # [(core_name, original_name, customer), ...]
    for c in customers:
        name = c.name.strip()
        if name:
            core = normalize_name(name)
            cust_entries.append((core, name, c))
        if c.contact_person:
            cp = c.contact_person.strip()
            if cp:
                core = normalize_name(cp)
                cust_entries.append((core, cp, c))

    def find_matching_customer(payer_name: str):
        """振込人名義から顧客を検索。核の名前で照合する。"""
        payer_core = normalize_name(payer_name)

        if not payer_core:
            return None

        # Pass 1: 核の名前が完全一致
        for core, orig, cust in cust_entries:
            if core and core == payer_core:
                return cust

        # Pass 2: 核の名前で部分一致（3文字以上の場合のみ）
        for core, orig, cust in cust_entries:
            if not core or len(core) < 3:
                continue
            if core in payer_core or payer_core in core:
                return cust

        return None

    # ★ FIX 3: 請求書を payments と一緒に eager load して正確な残額を計算
    all_unpaid_invoices = (
        db.query(models.Invoice)
        .options(joinedload(models.Invoice.payments))
        .filter(
            models.Invoice.company_id == current_user.company_id,
            models.Invoice.status.in_(["sent", "partial", "overdue"]),
        )
        .all()
    )

    # ★ FIX 4: このバッチ内で既にマッチした請求書IDを追跡し、二重消込を防ぐ
    matched_invoice_ids_this_batch = set()

    matched_count = 0
    results = []

    for txn in unmatched:
        matched_customer = find_matching_customer(txn.payer_name)

        if matched_customer:
            txn.matched_customer_id = matched_customer.id

            # この顧客の未払い請求書を検索（このバッチで未消込のもの優先）
            candidate_invoices = [
                inv for inv in all_unpaid_invoices
                if inv.customer_id == matched_customer.id
                and inv.id not in matched_invoice_ids_this_batch
            ]
            # 月が古い順にソート
            candidate_invoices.sort(key=lambda x: x.month)

            unpaid_invoice = None
            # まず金額一致の請求書を探す
            for inv in candidate_invoices:
                paid_so_far = sum(p.amount for p in (inv.payments or []))
                remaining = inv.total_amount - paid_so_far
                if remaining == txn.amount:
                    unpaid_invoice = inv
                    break
            # なければ最も古い未払い請求書
            if not unpaid_invoice and candidate_invoices:
                unpaid_invoice = candidate_invoices[0]

            if unpaid_invoice:
                txn.matched_invoice_id = unpaid_invoice.id
                txn.status = "matched"
                matched_invoice_ids_this_batch.add(unpaid_invoice.id)

                # 入金レコードを作成
                payment = models.Payment(
                    invoice_id=unpaid_invoice.id,
                    company_id=current_user.company_id,
                    amount=txn.amount,
                    payment_date=txn.transaction_date,
                    payment_method="bank_transfer",
                    notes=f"{txn.bank_name}自動消込 ({txn.payer_name})",
                )
                db.add(payment)

                # ★ FIX 5: 既存の payments + 今回の入金額で正しく判定
                total_paid = sum(p.amount for p in (unpaid_invoice.payments or [])) + txn.amount
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
            # ── ニアピン候補を探す ──
            # 名前は一致しなかったが、金額が一致 or 近い請求書を探す
            near = []
            for inv in all_unpaid_invoices:
                if inv.id in matched_invoice_ids_this_batch:
                    continue
                # 既存の入金を考慮した残額を計算
                paid_so_far = sum(p.amount for p in (inv.payments or []))
                remaining = inv.total_amount - paid_so_far
                if remaining <= 0:
                    continue
                # 完全一致 or 差額10%以内
                diff = abs(remaining - txn.amount)
                if remaining > 0 and diff <= remaining * 0.1:
                    cust = next((c for c in customers if c.id == inv.customer_id), None)
                    near.append({
                        "invoice_id": inv.id,
                        "customer_name": cust.name if cust else "不明",
                        "customer_id": inv.customer_id,
                        "invoice_month": inv.month,
                        "invoice_total": inv.total_amount,
                        "remaining": remaining,
                        "diff": diff,
                        "exact": diff == 0,
                    })
            # 差額が小さい順にソート、最大5件
            near.sort(key=lambda x: x["diff"])
            near = near[:5]

            results.append(MatchResult(
                transaction_id=txn.id,
                payer_name=txn.payer_name,
                amount=txn.amount,
                status="unmatched",
                near_matches=near if near else None,
            ))

    db.commit()
    return {"matched": matched_count, "total": len(unmatched), "results": [r.model_dump() for r in results]}


# ── 手動マッチング（ニアピン確定） ────────────────────────
@router.post("/manual-match")
def manual_match(
    body: ManualMatchRequest,
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
):
    """
    ニアピン候補を手動で確定し、入金消し込みを行う
    """
    txn = (
        db.query(models.BankTransaction)
        .filter_by(id=body.transaction_id, company_id=current_user.company_id)
        .first()
    )
    if not txn:
        raise HTTPException(404, "入金データが見つかりません")
    if txn.status != "unmatched":
        raise HTTPException(400, "この入金は既にマッチ済みです")

    # ★ FIX 6: payments を eager load して正確な残額計算
    inv = (
        db.query(models.Invoice)
        .options(joinedload(models.Invoice.payments))
        .filter_by(id=body.invoice_id, company_id=current_user.company_id)
        .first()
    )
    if not inv:
        raise HTTPException(404, "請求書が見つかりません")

    # マッチング確定
    txn.matched_customer_id = inv.customer_id
    txn.matched_invoice_id = inv.id
    txn.status = "matched"

    # 入金レコードを作成
    payment = models.Payment(
        invoice_id=inv.id,
        company_id=current_user.company_id,
        amount=txn.amount,
        payment_date=txn.transaction_date,
        payment_method="bank_transfer",
        notes=f"手動消込 ({txn.payer_name})",
    )
    db.add(payment)

    # 請求書ステータス更新
    total_paid = sum(p.amount for p in (inv.payments or [])) + txn.amount
    if total_paid >= inv.total_amount:
        inv.status = "paid"
        txn.status = "reconciled"
    else:
        inv.status = "partial"

    db.commit()

    cust = db.query(models.Customer).filter_by(id=inv.customer_id).first()
    return {
        "success": True,
        "message": f"{cust.name if cust else '不明'} の請求書に消し込みました",
        "status": txn.status,
    }


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
