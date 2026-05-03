import uuid
from datetime import datetime, timezone
from sqlalchemy import String, Integer, Float, Text, DateTime, ForeignKey, Boolean, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base


def utcnow():
    return datetime.now(timezone.utc)


class Company(Base):
    __tablename__ = "companies"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    users: Mapped[list["User"]] = relationship(back_populates="company")
    settings: Mapped["CompanySettings"] = relationship(back_populates="company", uselist=False)
    jobs: Mapped[list["Job"]] = relationship(back_populates="company")
    customers: Mapped[list["Customer"]] = relationship(back_populates="company")
    routes: Mapped[list["Route"]] = relationship(back_populates="company")
    invoices: Mapped[list["Invoice"]] = relationship(back_populates="company")


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    company_id: Mapped[str] = mapped_column(String, ForeignKey("companies.id"), nullable=False)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    role: Mapped[str] = mapped_column(String(50), nullable=False, default="staff")  # admin / staff
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    company: Mapped["Company"] = relationship(back_populates="users")
    jobs: Mapped[list["Job"]] = relationship(back_populates="user", foreign_keys="Job.user_id")
    assigned_jobs: Mapped[list["Job"]] = relationship(foreign_keys="Job.assigned_to")
    routes: Mapped[list["Route"]] = relationship(back_populates="driver")


class CompanySettings(Base):
    __tablename__ = "company_settings"

    company_id: Mapped[str] = mapped_column(String, ForeignKey("companies.id"), primary_key=True)
    # 会社情報
    company_address: Mapped[str] = mapped_column(Text, default="")
    company_phone: Mapped[str] = mapped_column(String(100), default="")
    company_invoice_no: Mapped[str] = mapped_column(String(100), default="")
    company_bank_info: Mapped[str] = mapped_column(Text, default="")
    # 基本料金
    base_price_m3: Mapped[int] = mapped_column(Integer, default=15000)
    # 搬出オプション
    stairs_2f_price: Mapped[int] = mapped_column(Integer, default=2000)
    stairs_3f_price: Mapped[int] = mapped_column(Integer, default=4000)
    far_parking_price: Mapped[int] = mapped_column(Integer, default=3000)
    # リサイクル4品目
    recycle_tv: Mapped[int] = mapped_column(Integer, default=3000)
    recycle_fridge: Mapped[int] = mapped_column(Integer, default=5000)
    recycle_washer: Mapped[int] = mapped_column(Integer, default=4000)
    recycle_ac: Mapped[int] = mapped_column(Integer, default=3500)
    # マットレス（サイズ別）
    mattress_single: Mapped[int] = mapped_column(Integer, default=3000)
    mattress_semi_double: Mapped[int] = mapped_column(Integer, default=4000)
    mattress_double: Mapped[int] = mapped_column(Integer, default=5000)
    mattress_queen_king: Mapped[int] = mapped_column(Integer, default=7000)
    # ソファー（人掛け別）
    sofa_1p: Mapped[int] = mapped_column(Integer, default=2000)
    sofa_2p: Mapped[int] = mapped_column(Integer, default=3500)
    sofa_3p: Mapped[int] = mapped_column(Integer, default=5000)
    sofa_large: Mapped[int] = mapped_column(Integer, default=8000)
    # その他特例品
    safe_price: Mapped[int] = mapped_column(Integer, default=15000)
    piano_price: Mapped[int] = mapped_column(Integer, default=20000)
    bike_price: Mapped[int] = mapped_column(Integer, default=5000)
    # カスタムAI料金項目 (JSON array of dicts)
    custom_ai_items: Mapped[str] = mapped_column(Text, default="[]")
    # 許可証期限管理
    license_expiry_date: Mapped[str | None] = mapped_column(String(20), nullable=True)
    # 決算月（1-12）
    fiscal_year_end_month: Mapped[int] = mapped_column(Integer, default=3)
    # 会社ロゴ・電子角印（Base64）
    company_logo: Mapped[str] = mapped_column(Text, default="")
    company_stamp: Mapped[str] = mapped_column(Text, default="")
    # 一般廃棄物単価マスタ (JSON: genre × frequency matrix)
    general_waste_pricing: Mapped[str] = mapped_column(Text, default="{}")

    # メールテンプレート（未入金リマインド用）
    unpaid_email_subject: Mapped[str] = mapped_column(String(255), default="【重要】未入金のお知らせ")
    unpaid_email_body: Mapped[str] = mapped_column(Text, default="{{customer_name}}様\n\n平素は格別のお引き立てを賜り、厚く御礼申し上げます。\n以下の請求書につきまして、お支払いの確認がとれておりません。\n\n請求月: {{month}}\n請求額: ¥{{amount}}\n支払期限: {{due_date}}\n\n既にお振込み済みの場合は、行き違いをご容赦ください。\n何卒よろしくお願い申し上げます。")

    # カスタムメール送信（SMTP）サーバー設定
    smtp_host: Mapped[str] = mapped_column(String(255), default="smtp.ocn.ne.jp")
    smtp_port: Mapped[int] = mapped_column(Integer, default=587)
    smtp_user: Mapped[str] = mapped_column(String(255), default="yamabun@sirius.ocn.ne.jp")
    smtp_password: Mapped[str] = mapped_column(String(255), default="")
    smtp_from_email: Mapped[str] = mapped_column(String(255), default="")

    # 処分先・委託先マスター (JSON array of strings)
    contractors_master: Mapped[str] = mapped_column(Text, default="[\"ホームケルン\", \"光アスコン\", \"旭興産業\", \"木材開発\", \"厳本金属\", \"京都有機資源\", \"HIRAYAMA\", \"大剛\", \"京都環境保全公社\", \"西山環境サービス\", \"家電リサイクル\"]")

    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    company: Mapped["Company"] = relationship(back_populates="settings")


class Job(Base):
    __tablename__ = "jobs"

    job_id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    company_id: Mapped[str] = mapped_column(String, ForeignKey("companies.id"), nullable=False)
    user_id: Mapped[str | None] = mapped_column(String, ForeignKey("users.id"), nullable=True)
    customer_id: Mapped[str | None] = mapped_column(String, ForeignKey("customers.id"), nullable=True)
    # 案件情報
    job_name: Mapped[str] = mapped_column(String(500), nullable=False)
    customer_name: Mapped[str] = mapped_column(String(255), default="")
    address: Mapped[str] = mapped_column(Text, default="")
    work_date: Mapped[str | None] = mapped_column(String(20), nullable=True)
    notes: Mapped[str] = mapped_column(Text, default="")
    # AI算出結果
    total_volume_m3: Mapped[float | None] = mapped_column(Float, nullable=True)
    ai_result: Mapped[str] = mapped_column(Text, default="")  # JSON文字列
    # 料金・状態
    price_total: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(50), default="pending")  # pending/confirmed/completed
    # 電子署名
    signature_data: Mapped[str] = mapped_column(Text, default="")  # Base64
    # ── 新規フィールド ──
    # 営業パイプライン: inquiry/estimate/negotiation/contract/scheduled/completed/lost
    pipeline_stage: Mapped[str] = mapped_column(String(50), default="inquiry")
    # 案件タイプ: store_removal/estate/welfare/general_waste/other
    job_type: Mapped[str] = mapped_column(String(50), default="other")
    # 担当営業
    assigned_to: Mapped[str | None] = mapped_column(String, ForeignKey("users.id"), nullable=True)
    # 写真（JSON配列: ["url1","url2",...]）
    photos: Mapped[str] = mapped_column(Text, default="[]")
    # ── 金額トラッキング ──
    estimated_price: Mapped[int | None] = mapped_column(Integer, nullable=True)  # 見積金額
    final_price: Mapped[int | None] = mapped_column(Integer, nullable=True)  # 成約/最終金額
    discount_amount: Mapped[int] = mapped_column(Integer, default=0)  # 割引額
    surcharge_amount: Mapped[int] = mapped_column(Integer, default=0)  # 追加料金
    price_notes: Mapped[str] = mapped_column(Text, default="")  # 金額変更理由
    # ── 山文様 拡張フォーム用 ──
    form_data: Mapped[str] = mapped_column(Text, default="{}")
    
    # タイムスタンプ
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    company: Mapped["Company"] = relationship(back_populates="jobs")
    user: Mapped["User | None"] = relationship(back_populates="jobs", foreign_keys=[user_id])
    assignee: Mapped["User | None"] = relationship(foreign_keys=[assigned_to])
    customer_rel: Mapped["Customer | None"] = relationship()
    comments: Mapped[list["JobComment"]] = relationship(back_populates="job", cascade="all, delete")


class Customer(Base):
    __tablename__ = "customers"
    __table_args__ = (
        Index('ix_customers_company_name', 'company_id', 'name'),
        Index('ix_customers_company_contract', 'company_id', 'contract_type'),
        Index('ix_customers_account_number', 'account_number'),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    company_id: Mapped[str] = mapped_column(String, ForeignKey("companies.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    address: Mapped[str] = mapped_column(Text, default="")
    phone: Mapped[str] = mapped_column(String(100), default="")
    contract_type: Mapped[str] = mapped_column(String(50), default="spot")
    # ── 新規フィールド ──
    email: Mapped[str] = mapped_column(String(255), default="")
    contact_person: Mapped[str] = mapped_column(String(255), default="")
    notes: Mapped[str] = mapped_column(Text, default="")
    contract_expiry_date: Mapped[str | None] = mapped_column(String(20), nullable=True)
    assigned_user_id: Mapped[str | None] = mapped_column(String, ForeignKey("users.id"), nullable=True)
    # ── 締め払い設定 ──
    # 締め日 (1-31, 31=月末締め, 20=20日締め, 15=15日締め)
    billing_closing_day: Mapped[int] = mapped_column(Integer, default=31)
    # 支払月オフセット (0=当月, 1=翌月, 2=翌々月)
    payment_due_month_offset: Mapped[int] = mapped_column(Integer, default=1)
    # 支払日 (1-31, 31=月末払い, 20=20日払い)
    payment_due_day: Mapped[int] = mapped_column(Integer, default=31)
    # ── 口座振替用 ──
    bank_code: Mapped[str] = mapped_column(String(4), default="")        # 銀行コード (4桁)
    branch_code: Mapped[str] = mapped_column(String(3), default="")      # 支店コード (3桁)
    account_type: Mapped[str] = mapped_column(String(1), default="1")    # 1=普通, 2=当座
    account_number: Mapped[str] = mapped_column(String(7), default="")   # 口座番号 (7桁)
    account_holder: Mapped[str] = mapped_column(String(30), default="")  # 口座名義 (カナ)
    # ── 山文様 拡張フォーム用 ──
    form_data: Mapped[str] = mapped_column(Text, default="{}")
    
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    company: Mapped["Company"] = relationship(back_populates="customers")
    assignee: Mapped["User | None"] = relationship(foreign_keys=[assigned_user_id])
    manifests: Mapped[list["Manifest"]] = relationship(back_populates="customer")
    invoices: Mapped[list["Invoice"]] = relationship(back_populates="customer")
    history_logs: Mapped[list["CustomerHistory"]] = relationship("CustomerHistory", back_populates="customer", cascade="all, delete-orphan", order_by="desc(CustomerHistory.created_at)")


class CustomerHistory(Base):
    __tablename__ = "customer_history"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    customer_id: Mapped[str] = mapped_column(String, ForeignKey("customers.id"), nullable=False)
    event_type: Mapped[str] = mapped_column(String(50), default="note")  # inquiry, claim, note, collection
    description: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    
    customer: Mapped["Customer"] = relationship("Customer", back_populates="history_logs")

class Manifest(Base):
    __tablename__ = "manifests"
    __table_args__ = (
        Index('ix_manifests_customer_status', 'customer_id', 'status'),
        Index('ix_manifests_customer_category', 'customer_id', 'waste_category'),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    job_id: Mapped[str | None] = mapped_column(String, ForeignKey("jobs.job_id"), nullable=True)
    customer_id: Mapped[str] = mapped_column(String, ForeignKey("customers.id"), nullable=False)
    waste_type: Mapped[str] = mapped_column(String(255), default="")
    issue_date: Mapped[str | None] = mapped_column(String(20), nullable=True)
    expected_return_date: Mapped[str | None] = mapped_column(String(20), nullable=True)
    actual_return_date: Mapped[str | None] = mapped_column(String(20), nullable=True)
    status: Mapped[str] = mapped_column(String(50), default="issued")
    # ── 新規フィールド ──
    manifest_number: Mapped[str] = mapped_column(String(100), default="")
    weight_kg: Mapped[float | None] = mapped_column(Float, nullable=True)
    unit_price_per_kg: Mapped[float] = mapped_column(Float, default=30.0)
    waste_category: Mapped[str] = mapped_column(String(50), default="industrial")  # industrial / general
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    customer: Mapped["Customer"] = relationship(back_populates="manifests")
    job: Mapped["Job | None"] = relationship()


# ── 請求書 ──────────────────────────────────────────────
class ItemTemplate(Base):
    __tablename__ = "item_templates"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    company_id: Mapped[str] = mapped_column(String, ForeignKey("companies.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)  # 品名 (例: 2tトラック積み放題)
    unit_price: Mapped[float] = mapped_column(Float, default=0)
    unit: Mapped[str] = mapped_column(String(50), default="式") # 単位 (式, kg, L, etc)
    description: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Invoice(Base):
    __tablename__ = "invoices"
    __table_args__ = (
        Index('ix_invoices_company_month', 'company_id', 'month'),
        Index('ix_invoices_company_status', 'company_id', 'status'),
        Index('ix_invoices_customer', 'customer_id'),
        Index('ix_invoices_company_month_status', 'company_id', 'month', 'status'),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    company_id: Mapped[str] = mapped_column(String, ForeignKey("companies.id"), nullable=False)
    customer_id: Mapped[str] = mapped_column(String, ForeignKey("customers.id"), nullable=False)
    # 請求対象月 (YYYY-MM)
    month: Mapped[str] = mapped_column(String(20), nullable=False)  # YYYY-MM
    total_amount: Mapped[int] = mapped_column(Integer, default=0)
    tax_amount: Mapped[int] = mapped_column(Integer, default=0)
    # draft / sent / paid / partial / overdue
    status: Mapped[str] = mapped_column(String(50), default="draft")
    invoice_type: Mapped[str] = mapped_column(String(20), default="mixed") # "spot", "subscription", "mixed"
    due_date: Mapped[str | None] = mapped_column(String(20), nullable=True)
    sent_at: Mapped[str | None] = mapped_column(String(20), nullable=True) # 請求書送付日
    last_reminded_at: Mapped[str | None] = mapped_column(String(20), nullable=True) # 未入金リマインド送信日時
    notes: Mapped[str] = mapped_column(Text, default="")
    # freee連携フラグ
    freee_synced: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    company: Mapped["Company"] = relationship(back_populates="invoices")
    customer: Mapped["Customer"] = relationship(back_populates="invoices")
    items: Mapped[list["InvoiceItem"]] = relationship(back_populates="invoice", cascade="all, delete")
    payments: Mapped[list["Payment"]] = relationship(back_populates="invoice", cascade="all, delete")


class InvoiceItem(Base):
    __tablename__ = "invoice_items"
    __table_args__ = (
        Index('ix_invoice_items_invoice', 'invoice_id'),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    invoice_id: Mapped[str] = mapped_column(String, ForeignKey("invoices.id"), nullable=False)
    description: Mapped[str] = mapped_column(String(500), default="")
    quantity: Mapped[float] = mapped_column(Float, default=1)
    unit: Mapped[str] = mapped_column(String(50), default="式")
    unit_price: Mapped[float] = mapped_column(Float, default=0)
    amount: Mapped[int] = mapped_column(Integer, default=0)
    # マニフェスト紐付け（産廃重量課金の場合）
    manifest_id: Mapped[str | None] = mapped_column(String, ForeignKey("manifests.id"), nullable=True)

    invoice: Mapped["Invoice"] = relationship(back_populates="items")
    manifest: Mapped["Manifest | None"] = relationship()


class Payment(Base):
    __tablename__ = "payments"
    __table_args__ = (
        Index('ix_payments_invoice', 'invoice_id'),
        Index('ix_payments_company', 'company_id'),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    invoice_id: Mapped[str] = mapped_column(String, ForeignKey("invoices.id"), nullable=False)
    company_id: Mapped[str] = mapped_column(String, ForeignKey("companies.id"), nullable=False)
    amount: Mapped[int] = mapped_column(Integer, default=0)
    payment_date: Mapped[str] = mapped_column(String(20), nullable=False)
    payment_method: Mapped[str] = mapped_column(String(50), default="bank_transfer")  # bank_transfer/cash/other
    notes: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    invoice: Mapped["Invoice"] = relationship(back_populates="payments")


class DailyReport(Base):
    __tablename__ = "daily_reports"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    company_id: Mapped[str] = mapped_column(String, ForeignKey("companies.id"), nullable=False)
    driver_id: Mapped[str] = mapped_column(String, ForeignKey("users.id"), nullable=False)
    customer_id: Mapped[str | None] = mapped_column(String, ForeignKey("customers.id"), nullable=True)
    customer_name: Mapped[str] = mapped_column(String(255), default="")
    
    report_date: Mapped[str] = mapped_column(String(20), nullable=False) # YYYY-MM-DD
    bag_count: Mapped[int] = mapped_column(Integer, default=0)
    weight_kg: Mapped[float] = mapped_column(Float, default=0.0)
    notes: Mapped[str] = mapped_column(Text, default="")
    
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    driver_rel: Mapped["User"] = relationship(foreign_keys=[driver_id])
    customer_rel: Mapped["Customer | None"] = relationship(foreign_keys=[customer_id])


class Route(Base):
    __tablename__ = "routes"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    company_id: Mapped[str] = mapped_column(String, ForeignKey("companies.id"), nullable=False)
    driver_id: Mapped[str | None] = mapped_column(String, ForeignKey("users.id"), nullable=True)
    date: Mapped[str] = mapped_column(String(20), nullable=False)
    vehicle_name: Mapped[str] = mapped_column(String(100), default="")
    status: Mapped[str] = mapped_column(String(50), default="draft")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    company: Mapped["Company"] = relationship(back_populates="routes")
    driver: Mapped["User | None"] = relationship(back_populates="routes")
    stops: Mapped[list["RouteStop"]] = relationship(back_populates="route", cascade="all, delete")


class RouteStop(Base):
    __tablename__ = "route_stops"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    route_id: Mapped[str] = mapped_column(String, ForeignKey("routes.id"), nullable=False)
    customer_id: Mapped[str] = mapped_column(String, ForeignKey("customers.id"), nullable=False)
    order_index: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(50), default="pending")
    notes: Mapped[str] = mapped_column(Text, default="")

    route: Mapped["Route"] = relationship(back_populates="stops")
    customer: Mapped["Customer"] = relationship()


# ── 案件コメント ──────────────────────────────────────────
class JobComment(Base):
    __tablename__ = "job_comments"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    job_id: Mapped[str] = mapped_column(String, ForeignKey("jobs.job_id"), nullable=False)
    user_id: Mapped[str] = mapped_column(String, ForeignKey("users.id"), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    job: Mapped["Job"] = relationship(back_populates="comments")
    user: Mapped["User"] = relationship()


# ── 銀行入金取込 ──────────────────────────────────────────
class BankTransaction(Base):
    __tablename__ = "bank_transactions"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    company_id: Mapped[str] = mapped_column(String, ForeignKey("companies.id"), nullable=False)
    transaction_date: Mapped[str] = mapped_column(String(20), nullable=False)
    amount: Mapped[int] = mapped_column(Integer, nullable=False)
    payer_name: Mapped[str] = mapped_column(String(255), default="")
    payer_name_kana: Mapped[str] = mapped_column(String(255), default="")  # カナ名義
    bank_name: Mapped[str] = mapped_column(String(100), default="京都銀行")
    # マッチング結果
    matched_customer_id: Mapped[str | None] = mapped_column(String, ForeignKey("customers.id"), nullable=True)
    matched_invoice_id: Mapped[str | None] = mapped_column(String, ForeignKey("invoices.id"), nullable=True)
    # unmatched / matched / reconciled
    status: Mapped[str] = mapped_column(String(50), default="unmatched")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    customer: Mapped["Customer | None"] = relationship()
    invoice: Mapped["Invoice | None"] = relationship()


# ── freee連携 ─────────────────────────────────────────────
class FreeeIntegration(Base):
    __tablename__ = "freee_integrations"

    company_id: Mapped[str] = mapped_column(String, ForeignKey("companies.id"), primary_key=True)
    access_token: Mapped[str] = mapped_column(Text, default="")
    refresh_token: Mapped[str] = mapped_column(Text, default="")
    token_expiry: Mapped[str | None] = mapped_column(String(30), nullable=True)
    freee_company_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


# ── 車両管理 ──────────────────────────────────────────────
class Vehicle(Base):
    __tablename__ = "vehicles"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    company_id: Mapped[str] = mapped_column(String, ForeignKey("companies.id"), nullable=False)
    # ナンバープレート
    plate_area: Mapped[str] = mapped_column(String(50), default="")        # 京都
    plate_class: Mapped[str] = mapped_column(String(20), default="")       # 831
    plate_kana: Mapped[str] = mapped_column(String(10), default="")        # の
    plate_number: Mapped[str] = mapped_column(String(20), default="")      # 9
    # 車両情報
    vehicle_number: Mapped[str] = mapped_column(String(20), default="")    # 号車
    maker: Mapped[str] = mapped_column(String(100), default="")            # メーカー
    code: Mapped[str] = mapped_column(String(20), default="")              # コード (A, B, C...)
    vehicle_type: Mapped[str] = mapped_column(String(100), default="")     # 車種
    max_capacity_kg: Mapped[int | None] = mapped_column(Integer, nullable=True)  # 最大積載量 (kg)
    driver_name: Mapped[str] = mapped_column(String(100), default="")      # 担当
    first_registration: Mapped[str | None] = mapped_column(String(20), nullable=True)  # 初年度登録
    inspection_expiry: Mapped[str | None] = mapped_column(String(20), nullable=True)   # 車検満了日
    tire_replacement_date: Mapped[str | None] = mapped_column(String(20), nullable=True)  # タイヤ交換日
    notes: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


# ── 許可証管理 ────────────────────────────────────────────
class Permit(Base):
    __tablename__ = "permits"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    company_id: Mapped[str] = mapped_column(String, ForeignKey("companies.id"), nullable=False)
    prefecture: Mapped[str] = mapped_column(String(100), default="")       # 自治体名
    permit_type: Mapped[str] = mapped_column(String(100), default="")      # 許可種類 (産廃/特管/入札参加資格等)
    permit_number: Mapped[str] = mapped_column(String(100), default="")    # 許可番号
    expiry_date: Mapped[str | None] = mapped_column(String(20), nullable=True)  # 許可有効年月日
    application_month: Mapped[str] = mapped_column(String(20), default="") # 申請月
    notes: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


# ── 産廃3社契約管理 ───────────────────────────────────────
class WasteContract(Base):
    __tablename__ = "waste_contracts"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    company_id: Mapped[str] = mapped_column(String, ForeignKey("companies.id"), nullable=False)
    contract_name: Mapped[str] = mapped_column(String(255), default="")    # 契約名
    contractor_name: Mapped[str] = mapped_column(String(255), default="")  # 排出事業者名
    disposal_company: Mapped[str] = mapped_column(String(255), default="") # 処分業者名
    transport_company: Mapped[str] = mapped_column(String(255), default="")# 運搬業者名
    waste_type: Mapped[str] = mapped_column(String(255), default="")       # 廃棄物種類
    contract_date: Mapped[str | None] = mapped_column(String(20), nullable=True)  # 契約日
    expiry_date: Mapped[str | None] = mapped_column(String(20), nullable=True)    # 契約有効期限
    document_url: Mapped[str] = mapped_column(Text, default="")            # 契約書URL
    notes: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


# ── 車両履歴（修理歴・事故歴・車検証） ───────────────────
class VehicleRecord(Base):
    __tablename__ = "vehicle_records"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    vehicle_id: Mapped[str] = mapped_column(String, ForeignKey("vehicles.id"), nullable=False)
    record_type: Mapped[str] = mapped_column(String(50), default="repair")  # repair/accident/inspection
    record_date: Mapped[str | None] = mapped_column(String(20), nullable=True)
    title: Mapped[str] = mapped_column(String(255), default="")
    description: Mapped[str] = mapped_column(Text, default="")
    file_url: Mapped[str] = mapped_column(Text, default="")   # 画像/PDF保存パス
    cost: Mapped[int | None] = mapped_column(Integer, nullable=True)  # 費用
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


# ── 研修資料管理 ──────────────────────────────────────────
class TrainingMaterial(Base):
    __tablename__ = "training_materials"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    company_id: Mapped[str] = mapped_column(String, ForeignKey("companies.id"), nullable=False)
    title: Mapped[str] = mapped_column(String(255), default="")
    file_url: Mapped[str] = mapped_column(Text, default="")
    file_type: Mapped[str] = mapped_column(String(50), default="")  # pdf/image
    notes: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
