"""銀行入金取込ルーター: CSVアップロード・自動マッチング・消し込み・名寄せ学習"""
import csv
import io
import re
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from pydantic import BaseModel
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import func
from app.database import get_db
from app import models, auth

router = APIRouter(prefix="/v1/bank", tags=["bank"])

# ── pykakasi (漢字→カタカナ変換) ───────────────────────────
try:
    import pykakasi
    _kakasi = pykakasi.kakasi()
    _kakasi.setMode("H", "K")  # ひらがな → カタカナ
    _kakasi.setMode("J", "K")  # 漢字 → カタカナ
    _kakasi.setMode("a", "K")  # ASCII → カタカナ
    _conv = _kakasi.getConverter()

    def to_katakana(text: str) -> str:
        """テキストを全角カタカナに変換"""
        return _conv.do(text)
except Exception:
    # pykakasi が使えない場合はそのまま返す
    def to_katakana(text: str) -> str:
        return text


# ── 名前正規化 ─────────────────────────────────────────────
STRIP_PATTERNS = [
    r'株式会社', r'有限会社', r'合同会社', r'合資会社', r'合名会社',
    r'一般社団法人', r'一般財団法人', r'社会福祉法人', r'医療法人',
    r'特定非営利活動法人', r'NPO法人',
    r'\(株\)', r'（株）', r'\(有\)', r'（有）', r'\(合\)', r'（合）',
    r'カ\)', r'カ）', r'\(カ', r'（カ', r'ユ\)', r'ユ）', r'\(ユ', r'（ユ',
    r'ド\)', r'ド）', r'\(ド', r'（ド',
    r'カブシキガイシャ', r'カブシキカイシャ', r'ユウゲンガイシャ', r'ユウゲンカイシャ',
    r'ゴウドウガイシャ', r'ゴウドウカイシャ',
    r'御中', r'様',
]

def normalize_name(name: str) -> str:
    """法人格・記号を除去し、核となる名前を抽出する"""
    s = name.strip()
    for pat in STRIP_PATTERNS:
        s = re.sub(pat, '', s)
    s = re.sub(r'[\s　・\-\.\(\)（）「」\u3000]+', '', s)
    return s.strip()


def normalize_for_kana_match(name: str) -> str:
    """名前を正規化 + カタカナ変換して照合用文字列を作る"""
    core = normalize_name(name)
    return to_katakana(core)


# ── 監査ログヘルパー ───────────────────────────────────────
def _audit(db: Session, user: models.User, action: str, target_type: str, target_id: str, details: str):
    log = models.AuditLog(
        company_id=user.company_id,
        user_id=user.id,
        user_name=user.username,
        action=action,
        target_type=target_type,
        target_id=target_id,
        details=details,
    )
    db.add(log)


# ── Schemas ────────────────────────────────────────────
class MatchResult(BaseModel):
    transaction_id: str
    payer_name: str
    amount: int
    status: str
    matched_customer_name: str | None = None
    matched_invoice_id: str | None = None
    near_matches: list[dict] | None = None


class ManualMatchRequest(BaseModel):
    transaction_id: str
    invoice_id: str


class UndoMatchRequest(BaseModel):
    transaction_id: str


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
    重複取込防止: 同じ日付・名義・金額の組み合わせがあればスキップ
    """
    content = await file.read()
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

        # 重複取込防止
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
            payer_name_kana=payer,
            bank_name=bank_name_str,
            status="unmatched",
        )
        db.add(txn)
        imported += 1

    db.commit()
    _audit(db, current_user, "bank_csv_upload", "bank_transaction", "",
           f"取込: {imported}件, スキップ: {skipped}件, 銀行: {bank_type}")
    db.commit()
    return {"imported": imported, "skipped": skipped}


# ── 自動マッチング ──────────────────────────────────────
@router.post("/auto-match")
def auto_match(
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
):
    """
    未マッチの銀行入金を自動マッチング
    優先順: エイリアス(学習済み) → カナ変換マッチ → ニアピン候補表示
    """
    unmatched = (
        db.query(models.BankTransaction)
        .filter_by(company_id=current_user.company_id, status="unmatched")
        .all()
    )

    customers = db.query(models.Customer).filter_by(company_id=current_user.company_id).all()

    # エイリアス（学習済み名寄せ）を取得
    aliases = (
        db.query(models.PayerNameAlias)
        .filter_by(company_id=current_user.company_id)
        .all()
    )
    alias_map = {a.payer_name.strip(): a.customer_id for a in aliases}

    # 顧客名の正規化＋カナ変換マップ
    cust_entries = []  # [(kana_core, original_name, customer), ...]
    for c in customers:
        name = c.name.strip()
        if name:
            core = normalize_name(name)
            kana = normalize_for_kana_match(name)
            cust_entries.append((core, kana, name, c))
        if c.contact_person:
            cp = c.contact_person.strip()
            if cp:
                core = normalize_name(cp)
                kana = normalize_for_kana_match(cp)
                cust_entries.append((core, kana, cp, c))

    def find_matching_customer(payer_name: str):
        """振込人名義から顧客を検索"""
        pn = payer_name.strip()

        # Pass 0: エイリアス（学習済み） ─ 最優先
        if pn in alias_map:
            cust_id = alias_map[pn]
            cust = next((c for c in customers if c.id == cust_id), None)
            if cust:
                return cust

        payer_core = normalize_name(pn)
        payer_kana = normalize_for_kana_match(pn)

        if not payer_core:
            return None

        # Pass 1: 核の名前が完全一致
        for core, kana, orig, cust in cust_entries:
            if core and core == payer_core:
                return cust

        # Pass 2: カナ変換後に完全一致
        if payer_kana:
            for core, kana, orig, cust in cust_entries:
                if kana and kana == payer_kana:
                    return cust

        # Pass 3: 核の名前で部分一致（3文字以上）
        for core, kana, orig, cust in cust_entries:
            if not core or len(core) < 3:
                continue
            if core in payer_core or payer_core in core:
                return cust

        # Pass 4: カナで部分一致（3文字以上）
        if payer_kana and len(payer_kana) >= 3:
            for core, kana, orig, cust in cust_entries:
                if not kana or len(kana) < 3:
                    continue
                if kana in payer_kana or payer_kana in kana:
                    return cust

        return None

    # 請求書を payments と一緒に eager load
    all_unpaid_invoices = (
        db.query(models.Invoice)
        .options(joinedload(models.Invoice.payments))
        .filter(
            models.Invoice.company_id == current_user.company_id,
            models.Invoice.status.in_(["sent", "partial", "overdue"]),
        )
        .all()
    )

    matched_invoice_ids_this_batch = set()
    matched_count = 0
    results = []

    for txn in unmatched:
        matched_customer = find_matching_customer(txn.payer_name)

        if matched_customer:
            txn.matched_customer_id = matched_customer.id

            candidate_invoices = [
                inv for inv in all_unpaid_invoices
                if inv.customer_id == matched_customer.id
                and inv.id not in matched_invoice_ids_this_batch
            ]
            candidate_invoices.sort(key=lambda x: x.month)

            unpaid_invoice = None
            for inv in candidate_invoices:
                paid_so_far = sum(p.amount for p in (inv.payments or []))
                remaining = inv.total_amount - paid_so_far
                if remaining == txn.amount:
                    unpaid_invoice = inv
                    break
            if not unpaid_invoice and candidate_invoices:
                unpaid_invoice = candidate_invoices[0]

            if unpaid_invoice:
                txn.matched_invoice_id = unpaid_invoice.id
                txn.status = "matched"
                matched_invoice_ids_this_batch.add(unpaid_invoice.id)

                payment = models.Payment(
                    invoice_id=unpaid_invoice.id,
                    company_id=current_user.company_id,
                    amount=txn.amount,
                    payment_date=txn.transaction_date,
                    payment_method="bank_transfer",
                    notes=f"{txn.bank_name}自動消込 ({txn.payer_name})",
                )
                db.add(payment)

                total_paid = sum(p.amount for p in (unpaid_invoice.payments or [])) + txn.amount
                if total_paid >= unpaid_invoice.total_amount:
                    unpaid_invoice.status = "paid"
                    txn.status = "reconciled"
                else:
                    unpaid_invoice.status = "partial"

                matched_count += 1
                _audit(db, current_user, "bank_matched", "bank_transaction", txn.id,
                       f"自動消込: {txn.payer_name} → {matched_customer.name} ¥{txn.amount:,}")

            results.append(MatchResult(
                transaction_id=txn.id,
                payer_name=txn.payer_name,
                amount=txn.amount,
                status=txn.status,
                matched_customer_name=matched_customer.name,
                matched_invoice_id=txn.matched_invoice_id,
            ))
        else:
            # ニアピン候補
            near = []
            for inv in all_unpaid_invoices:
                if inv.id in matched_invoice_ids_this_batch:
                    continue
                paid_so_far = sum(p.amount for p in (inv.payments or []))
                remaining = inv.total_amount - paid_so_far
                if remaining <= 0:
                    continue
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


# ── 手動マッチング（ニアピン確定 + 名寄せ学習） ───────────────
@router.post("/manual-match")
def manual_match(
    body: ManualMatchRequest,
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
):
    txn = (
        db.query(models.BankTransaction)
        .filter_by(id=body.transaction_id, company_id=current_user.company_id)
        .first()
    )
    if not txn:
        raise HTTPException(404, "入金データが見つかりません")
    if txn.status != "unmatched":
        raise HTTPException(400, "この入金は既にマッチ済みです")

    inv = (
        db.query(models.Invoice)
        .options(joinedload(models.Invoice.payments))
        .filter_by(id=body.invoice_id, company_id=current_user.company_id)
        .first()
    )
    if not inv:
        raise HTTPException(404, "請求書が見つかりません")

    txn.matched_customer_id = inv.customer_id
    txn.matched_invoice_id = inv.id
    txn.status = "matched"

    payment = models.Payment(
        invoice_id=inv.id,
        company_id=current_user.company_id,
        amount=txn.amount,
        payment_date=txn.transaction_date,
        payment_method="bank_transfer",
        notes=f"手動消込 ({txn.payer_name})",
    )
    db.add(payment)

    total_paid = sum(p.amount for p in (inv.payments or [])) + txn.amount
    if total_paid >= inv.total_amount:
        inv.status = "paid"
        txn.status = "reconciled"
    else:
        inv.status = "partial"

    # ★ 名寄せ学習: この振込人名 = この顧客 を記憶する
    payer_stripped = txn.payer_name.strip()
    existing_alias = (
        db.query(models.PayerNameAlias)
        .filter_by(company_id=current_user.company_id, payer_name=payer_stripped)
        .first()
    )
    if not existing_alias:
        alias = models.PayerNameAlias(
            company_id=current_user.company_id,
            payer_name=payer_stripped,
            customer_id=inv.customer_id,
        )
        db.add(alias)

    cust = db.query(models.Customer).filter_by(id=inv.customer_id).first()
    _audit(db, current_user, "bank_manual_match", "bank_transaction", txn.id,
           f"手動消込: {txn.payer_name} → {cust.name if cust else '不明'} ¥{txn.amount:,}")

    db.commit()
    return {
        "success": True,
        "message": f"{cust.name if cust else '不明'} の請求書に消し込みました（名寄せ学習済み）",
        "status": txn.status,
    }


# ── 消込取り消し ────────────────────────────────────────────
@router.post("/undo-match")
def undo_match(
    body: UndoMatchRequest,
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
):
    """消込を取り消し、入金レコードを削除してステータスを戻す"""
    txn = (
        db.query(models.BankTransaction)
        .filter_by(id=body.transaction_id, company_id=current_user.company_id)
        .first()
    )
    if not txn:
        raise HTTPException(404, "入金データが見つかりません")
    if txn.status == "unmatched":
        raise HTTPException(400, "この入金はまだ消込されていません")

    invoice_id = txn.matched_invoice_id
    old_status = txn.status

    # 該当する自動消込の Payment を検索・削除
    if invoice_id:
        payments_to_delete = (
            db.query(models.Payment)
            .filter(
                models.Payment.invoice_id == invoice_id,
                models.Payment.company_id == current_user.company_id,
                models.Payment.amount == txn.amount,
                models.Payment.notes.contains(txn.payer_name),
            )
            .all()
        )
        for p in payments_to_delete:
            db.delete(p)

        # 請求書ステータスを再計算
        inv = (
            db.query(models.Invoice)
            .options(joinedload(models.Invoice.payments))
            .filter_by(id=invoice_id)
            .first()
        )
        if inv:
            remaining_paid = sum(
                p.amount for p in (inv.payments or [])
                if p.id not in {pp.id for pp in payments_to_delete}
            )
            if remaining_paid >= inv.total_amount:
                inv.status = "paid"
            elif remaining_paid > 0:
                inv.status = "partial"
            else:
                # 送信済みなら sent、それ以外は overdue かどうか判定が必要
                inv.status = "sent"

    # トランザクションをリセット
    txn.matched_customer_id = None
    txn.matched_invoice_id = None
    txn.status = "unmatched"

    _audit(db, current_user, "bank_undo_match", "bank_transaction", txn.id,
           f"消込取消: {txn.payer_name} ¥{txn.amount:,} (旧ステータス: {old_status})")

    db.commit()
    return {"success": True, "message": "消込を取り消しました"}


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


# ── 監査ログ取得 ────────────────────────────────────────
@router.get("/audit-logs")
def get_audit_logs(
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
):
    logs = (
        db.query(models.AuditLog)
        .filter_by(company_id=current_user.company_id)
        .order_by(models.AuditLog.created_at.desc())
        .limit(100)
        .all()
    )
    return [
        {
            "id": l.id,
            "user_name": l.user_name,
            "action": l.action,
            "target_type": l.target_type,
            "target_id": l.target_id,
            "details": l.details,
            "created_at": l.created_at.isoformat() if l.created_at else "",
        }
        for l in logs
    ]
