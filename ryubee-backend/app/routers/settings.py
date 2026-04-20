"""設定ルーター: 料金マスタ + 会社情報の取得・保存"""
import json
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session
from app.database import get_db
from app import models, auth

router = APIRouter(prefix="/v1/settings", tags=["settings"])


class SettingsSchema(BaseModel):
    # 会社情報
    company_name: str = ""
    company_address: str = ""
    company_phone: str = ""
    company_invoice_no: str = ""
    company_bank_info: str = ""
    # 基本料金
    base_price_m3: int = 15000
    # 搬出オプション
    stairs_2f_price: int = 2000
    stairs_3f_price: int = 4000
    far_parking_price: int = 3000
    # リサイクル4品目
    recycle_tv: int = 3000
    recycle_fridge: int = 5000
    recycle_washer: int = 4000
    recycle_ac: int = 3500
    # マットレス
    mattress_single: int = 3000
    mattress_semi_double: int = 4000
    mattress_double: int = 5000
    mattress_queen_king: int = 7000
    # ソファー
    sofa_1p: int = 2000
    sofa_2p: int = 3500
    sofa_3p: int = 5000
    sofa_large: int = 8000
    # その他
    safe_price: int = 15000
    piano_price: int = 20000
    bike_price: int = 5000
    custom_ai_items: list[dict] = []

    # 決算月
    fiscal_year_end_month: int = 3
    # メールテンプレート
    unpaid_email_subject: str = "【重要】未入金のお知らせ"
    unpaid_email_body: str = "{{customer_name}}様\n\n平素は格別のお引き立てを賜り、厚く御礼申し上げます。\n以下の請求書につきまして、お支払いの確認がとれておりません。\n\n請求月: {{month}}\n請求額: ¥{{amount}}\n支払期限: {{due_date}}\n\n既にお振込み済みの場合は、行き違いをご容赦ください。\n何卒よろしくお願い申し上げます。"

    model_config = {"from_attributes": True}
    # ロゴ・電子角印 (Base64 data URL)
    company_logo: str = ""
    company_stamp: str = ""
    # 一般廃棄物単価マスタ (genre × frequency)
    general_waste_pricing: dict = {}


@router.get("", response_model=SettingsSchema)
def get_settings(
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
):
    """自社の料金設定を取得（全ロールが取得可能）"""
    rec = db.get(models.CompanySettings, current_user.company_id)
    if not rec:
        # CompanySettings が無ければデフォルト値で自動生成
        rec = models.CompanySettings(company_id=current_user.company_id)
        db.add(rec)
        db.commit()
        db.refresh(rec)

    # company_name は Company テーブルから
    data_dict = {col.name: getattr(rec, col.name) for col in rec.__table__.columns}
    data_dict["company_name"] = rec.company.name
    try:
        data_dict["custom_ai_items"] = json.loads(rec.custom_ai_items) if rec.custom_ai_items else []
    except Exception:
        data_dict["custom_ai_items"] = []
    try:
        data_dict["general_waste_pricing"] = json.loads(rec.general_waste_pricing) if rec.general_waste_pricing else {}
    except Exception:
        data_dict["general_waste_pricing"] = {}
    return SettingsSchema(**data_dict)


@router.put("", response_model=SettingsSchema)
def update_settings(
    body: SettingsSchema,
    current_user: models.User = Depends(auth.require_admin),  # 管理者のみ変更可
    db: Session = Depends(get_db),
):
    """設定を保存（管理者のみ）"""
    rec = db.get(models.CompanySettings, current_user.company_id)
    if not rec:
        rec = models.CompanySettings(company_id=current_user.company_id)
        db.add(rec)

    # 会社名は Company テーブルを更新
    if body.company_name:
        rec.company.name = body.company_name

    # CompanySettings フィールドを一括更新
    exclude = {"company_name", "custom_ai_items", "general_waste_pricing"}
    for field, val in body.model_dump(exclude=exclude).items():
        if hasattr(rec, field):
            setattr(rec, field, val)

    rec.custom_ai_items = json.dumps(body.custom_ai_items, ensure_ascii=False)
    rec.general_waste_pricing = json.dumps(body.general_waste_pricing, ensure_ascii=False)

    db.commit()
    db.refresh(rec)

    data_dict = {col.name: getattr(rec, col.name) for col in rec.__table__.columns}
    data_dict["company_name"] = rec.company.name
    try:
        data_dict["custom_ai_items"] = json.loads(rec.custom_ai_items) if rec.custom_ai_items else []
    except Exception:
        data_dict["custom_ai_items"] = []
    try:
        data_dict["general_waste_pricing"] = json.loads(rec.general_waste_pricing) if rec.general_waste_pricing else {}
    except Exception:
        data_dict["general_waste_pricing"] = {}
    return SettingsSchema(**data_dict)
