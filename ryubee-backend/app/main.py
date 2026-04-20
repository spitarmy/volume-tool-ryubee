import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from app.database import engine, Base
from app.routers import (
    auth, jobs, admin, customers, manifests, routes,
    invoices, payments, settings, bank, freee, templates, volume, daily_reports,
    company_data
)
# テーブルを自動作成（本番ではAlembicマイグレーション推奨）
Base.metadata.create_all(bind=engine)

# 起動時の自動マイグレーション（新カラム追加 — PostgreSQL互換）
try:
    with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as _conn:
        _sa = __import__('sqlalchemy')
        # 各カラム追加を個別に実行（既に存在する場合はDB側でエラーになるが無視する）
        _migrations = [
            ("company_settings", "company_logo", "TEXT DEFAULT ''"),
            ("company_settings", "company_stamp", "TEXT DEFAULT ''"),
            ("company_settings", "general_waste_pricing", "TEXT DEFAULT '{}'"),
            ("customers", "bank_code", "VARCHAR(4) DEFAULT ''"),
            ("customers", "branch_code", "VARCHAR(3) DEFAULT ''"),
            ("customers", "account_type", "VARCHAR(1) DEFAULT '1'"),
            ("customers", "account_number", "VARCHAR(7) DEFAULT ''"),
            ("customers", "account_holder", "VARCHAR(30) DEFAULT ''"),
            ("company_settings", "unpaid_email_subject", "VARCHAR(255) DEFAULT '【重要】未入金のお知らせ'"),
            ("company_settings", "unpaid_email_body", "TEXT"),
            ("company_settings", "smtp_host", "VARCHAR(255) DEFAULT 'smtp.ocn.ne.jp'"),
            ("company_settings", "smtp_port", "INTEGER DEFAULT 587"),
            ("company_settings", "smtp_user", "VARCHAR(255) DEFAULT 'yamabun@sirius.ocn.ne.jp'"),
            ("company_settings", "smtp_password", "VARCHAR(255) DEFAULT ''"),
            ("users", "role", "VARCHAR(20) DEFAULT 'staff'"),
            ("company_settings", "contractors_master", "TEXT DEFAULT '[\"ホームケルン\", \"光アスコン\", \"旭興産業\", \"木材開発\", \"厳本金属\", \"京都有機資源\", \"HIRAYAMA\", \"大剛\", \"京都環境保全公社\", \"西山環境サービス\", \"家電リサイクル\"]'"),
        ]
        for _table, _col, _coltype in _migrations:
            try:
                _conn.execute(_sa.text(f"ALTER TABLE {_table} ADD COLUMN {_col} {_coltype}"))
            except Exception:
                pass
except Exception as _e:
    print(f"Auto-migration skipped: {_e}")

app = FastAPI(
    title="Ryu兵衛 API",
    description="立米AI現場見積ツール バックエンドAPI",
    version="1.0.0",
)

os.makedirs("uploads", exist_ok=True)
app.mount("/uploads", StaticFiles(directory="uploads"), name="uploads")

# ── CORS（Vercel/GitHub Pagesフロントからのアクセスを許可）────────────
env_origin = os.getenv("FRONTEND_ORIGIN", "")
allowed_origins = [
    "https://spitarmy.github.io",
    "http://localhost:3000",
    "http://127.0.0.1:5500",
    "http://localhost:5500",
    "http://localhost:5501",
    "https://ryubee-frontend-app.onrender.com",
    "https://volumary-app.onrender.com"
]
if env_origin and env_origin != "*":
    allowed_origins.append(env_origin)

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── ルーターを登録 ──────────────────────────────────────
app.include_router(auth.router)
app.include_router(settings.router)
app.include_router(jobs.router)
app.include_router(admin.router)
app.include_router(customers.router)
app.include_router(manifests.router)
app.include_router(routes.router)
app.include_router(invoices.router)
app.include_router(payments.router)
app.include_router(bank.router)
app.include_router(freee.router)
app.include_router(templates.router)
app.include_router(volume.router)
app.include_router(daily_reports.router)
app.include_router(company_data.router)

try:
    from app.routers import auto_debit
    app.include_router(auto_debit.router)
except ImportError as _e:
    print(f"auto_debit router not loaded: {_e}")


@app.get("/")
def root():
    return {"message": "Ryu兵衛 API is running 🚀", "docs": "/docs"}

from sqlalchemy.orm import Session
from app.database import get_db, engine
from sqlalchemy import text

@app.get("/health")
def health():
    return {"status": "ok"}
