"""認証ルーター: 新規登録・ログイン・ユーザー情報取得"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr
from sqlalchemy.orm import Session
from app.database import get_db
from app import models, auth

router = APIRouter(prefix="/v1/auth", tags=["auth"])


# ── Schemas ────────────────────────────────────────────
class RegisterRequest(BaseModel):
    company_name: str
    email: EmailStr
    password: str
    name: str = ""


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class UserOut(BaseModel):
    id: str
    email: str
    name: str
    role: str
    company_id: str

    model_config = {"from_attributes": True}


class TokenResponse(BaseModel):
    token: str
    user: UserOut


# ── Endpoints ──────────────────────────────────────────
@router.post("/register", response_model=TokenResponse)
def register(req: RegisterRequest, db: Session = Depends(get_db)):
    """新規業者登録 + 初期管理者ユーザー作成"""
    # 2社のみ許可する制約（マスター用＋山文様）
    if db.query(models.Company).count() >= 2:
        raise HTTPException(403, "新規の業者登録は制限されています。管理者の招待機能をご利用ください。")

    if db.query(models.User).filter_by(email=req.email).first():
        raise HTTPException(400, "このメールアドレスはすでに登録されています")

    company = models.Company(name=req.company_name)
    db.add(company)
    db.flush()  # company.id を確定

    # 初期設定レコードも同時に作成
    settings = models.CompanySettings(company_id=company.id)
    db.add(settings)

    user = models.User(
        company_id=company.id,
        email=req.email,
        password_hash=auth.hash_password(req.password),
        name=req.name or req.email.split("@")[0],
        role="admin",  # 最初のユーザーは管理者
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    token = auth.create_access_token({"sub": user.id, "company_id": company.id, "role": user.role})
    return TokenResponse(token=token, user=UserOut.model_validate(user))


@router.post("/login", response_model=TokenResponse)
def login(req: LoginRequest, db: Session = Depends(get_db)):
    user = db.query(models.User).filter_by(email=req.email).first()
    if not user or not auth.verify_password(req.password, user.password_hash):
        raise HTTPException(401, "メールアドレスまたはパスワードが違います")

    token = auth.create_access_token({"sub": user.id, "company_id": user.company_id, "role": user.role})
    return TokenResponse(token=token, user=UserOut.model_validate(user))


@router.get("/me", response_model=UserOut)
def me(current_user: models.User = Depends(auth.get_current_user)):
    return current_user


class InviteRequest(BaseModel):
    email: EmailStr
    password: str
    name: str = ""
    role: str = "staff"  # staff or admin


@router.post("/invite", response_model=UserOut)
def invite_user(
    req: InviteRequest,
    current_user: models.User = Depends(auth.require_admin),
    db: Session = Depends(get_db),
):
    """管理者が同じ会社のスタッフを追加招待する"""
    if db.query(models.User).filter_by(email=req.email).first():
        raise HTTPException(400, "このメールアドレスはすでに登録されています")

    user = models.User(
        company_id=current_user.company_id,
        email=req.email,
        password_hash=auth.hash_password(req.password),
        name=req.name or req.email.split("@")[0],
        role=req.role,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user
