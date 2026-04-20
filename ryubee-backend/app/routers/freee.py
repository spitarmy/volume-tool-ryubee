"""freee会計連携ルーター: OAuth認証・取引同期"""
import os
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
import httpx
from app.database import get_db
from app import models, auth

router = APIRouter(prefix="/v1/freee", tags=["freee"])

FREEE_APP_ID = os.getenv("FREEE_APP_ID", "")
FREEE_APP_SECRET = os.getenv("FREEE_APP_SECRET", "")
FREEE_REDIRECT_URI = os.getenv("FREEE_REDIRECT_URI", "http://localhost:5500/freee-callback.html")
FREEE_AUTH_URL = "https://accounts.secure.freee.co.jp/public_api/authorize"
FREEE_TOKEN_URL = "https://accounts.secure.freee.co.jp/public_api/token"
FREEE_API_BASE = "https://api.freee.co.jp"


# ── OAuth認可URL生成 ──────────────────────────────────
@router.get("/auth-url")
def get_auth_url(current_user: models.User = Depends(auth.get_current_user)):
    if not FREEE_APP_ID:
        raise HTTPException(400, "freee APP_IDが設定されていません。環境変数FREEE_APP_IDを設定してください。")
    url = (
        f"{FREEE_AUTH_URL}?client_id={FREEE_APP_ID}"
        f"&redirect_uri={FREEE_REDIRECT_URI}"
        f"&response_type=code&prompt=consent"
    )
    return {"auth_url": url}


# ── OAuthコールバック ─────────────────────────────────
@router.post("/callback")
def oauth_callback(
    code: str = Query(...),
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
):
    resp = httpx.post(FREEE_TOKEN_URL, data={
        "grant_type": "authorization_code",
        "client_id": FREEE_APP_ID,
        "client_secret": FREEE_APP_SECRET,
        "code": code,
        "redirect_uri": FREEE_REDIRECT_URI,
    })
    if resp.status_code != 200:
        raise HTTPException(400, f"freeeトークン取得エラー: {resp.text}")

    data = resp.json()

    # freeeの事業所IDを取得
    me_resp = httpx.get(f"{FREEE_API_BASE}/api/1/users/me", headers={
        "Authorization": f"Bearer {data['access_token']}"
    })
    freee_company_id = None
    if me_resp.status_code == 200:
        companies = me_resp.json().get("user", {}).get("companies", [])
        if companies:
            freee_company_id = companies[0]["id"]

    # トークンを保存/更新
    integration = db.query(models.FreeeIntegration).filter_by(
        company_id=current_user.company_id
    ).first()

    if integration:
        integration.access_token = data["access_token"]
        integration.refresh_token = data.get("refresh_token", "")
        integration.freee_company_id = freee_company_id
    else:
        integration = models.FreeeIntegration(
            company_id=current_user.company_id,
            access_token=data["access_token"],
            refresh_token=data.get("refresh_token", ""),
            freee_company_id=freee_company_id,
        )
        db.add(integration)

    db.commit()
    return {"status": "connected", "freee_company_id": freee_company_id}


# ── 接続ステータス確認 ────────────────────────────────
@router.get("/status")
def get_status(
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
):
    integration = db.query(models.FreeeIntegration).filter_by(
        company_id=current_user.company_id
    ).first()
    if not integration or not integration.access_token:
        return {"connected": False}
    return {"connected": True, "freee_company_id": integration.freee_company_id}


# ── 請求書→freee取引同期 ──────────────────────────────
@router.post("/sync-invoice/{invoice_id}")
def sync_invoice(
    invoice_id: str,
    current_user: models.User = Depends(auth.require_admin),
    db: Session = Depends(get_db),
):
    integration = db.query(models.FreeeIntegration).filter_by(
        company_id=current_user.company_id
    ).first()
    if not integration or not integration.access_token:
        raise HTTPException(400, "freeeに接続されていません")

    invoice = db.query(models.Invoice).filter_by(
        id=invoice_id, company_id=current_user.company_id
    ).first()
    if not invoice:
        raise HTTPException(404, "請求書が見つかりません")

    customer = db.query(models.Customer).filter_by(id=invoice.customer_id).first()

    # freee取引を作成（売上）
    deal_data = {
        "company_id": integration.freee_company_id,
        "issue_date": invoice.month + "-01",
        "type": "income",
        "details": [
            {
                "account_item_id": 0,  # 売上高（実際には事業所の勘定科目IDが必要）
                "tax_code": 2,  # 課税売上10%
                "amount": invoice.total_amount,
                "description": f"{customer.name if customer else ''} {invoice.month}分",
            }
        ],
    }

    resp = httpx.post(
        f"{FREEE_API_BASE}/api/1/deals",
        json=deal_data,
        headers={"Authorization": f"Bearer {integration.access_token}"},
    )

    if resp.status_code in (200, 201):
        invoice.freee_synced = True
        db.commit()
        return {"status": "synced", "freee_deal_id": resp.json().get("deal", {}).get("id")}
    else:
        raise HTTPException(400, f"freee同期エラー: {resp.text}")
