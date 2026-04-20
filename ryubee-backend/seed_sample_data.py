import json
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.models import Customer, Job, User
from dotenv import load_dotenv
import os

load_dotenv()
SQLALCHEMY_DATABASE_URL = os.getenv("DATABASE_URL")
if SQLALCHEMY_DATABASE_URL and SQLALCHEMY_DATABASE_URL.startswith("postgres://"):
    SQLALCHEMY_DATABASE_URL = SQLALCHEMY_DATABASE_URL.replace("postgres://", "postgresql://", 1)

engine = create_engine(SQLALCHEMY_DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
db = SessionLocal()

# Find test user/company
user = db.query(User).first()
if not user:
    print("ユーザーが存在しません")
    exit(1)

company_id = user.company_id

sample_customers = [
    {
        "name": "株式会社 京都和風リゾート",
        "address": "京都市東山区祇園町...",
        "phone": "075-123-4567",
        "email": "hotel@kyoto-wafuresort.example.com",
        "contact_person": "田中 マネージャー",
        "contract_type": "subscription",
        "contract_expiry_date": "2027-03-31",
        "billing_closing_day": 31,
        "payment_due_month_offset": 1,
        "payment_due_day": 31,
        "form_data": {
            "branch_name": "祇園本店",
            "branch_address": "京都市東山区祇園町...",
            "industry_type": "飲食店",
            "average_volume": "3m3/週",
            "collection_general": "週2回",
            "collection_recycle": "週1回",
            "collection_plastic": "月2回",
            "collection_paper": "週1回",
            "business_hours": "11:00 - 22:00",
            "regular_holiday": "水曜日",
            "collection_start_date": "2026-04-01",
            "payment_method": "自動引落し",
            "billing_address": "京都市中京区河原町...",
            "billing_email": "accounting@kyoto-wafuresort.example.com",
            "billing_contact": "経理部 佐藤",
            "pricing_list": [
                {"item": "一般ごみ", "price": "45", "unit": "kg"},
                {"item": "資源ごみ（缶ビン）", "price": "1000", "unit": "月額"},
                {"item": "段ボール", "price": "0", "unit": "kg(無料引取)"}
            ]
        }
    },
    {
        "name": "高辻グリーンマンション 管理組合",
        "address": "京都市下京区高辻通...",
        "phone": "075-987-6543",
        "email": "kumiai@takatsuji-green.example.com",
        "contact_person": "鈴木 理事長",
        "contract_type": "subscription",
        "contract_expiry_date": "2028-03-31",
        "billing_closing_day": 20,
        "payment_due_month_offset": 1,
        "payment_due_day": 20,
        "form_data": {
            "branch_name": "高辻グリーンマンション",
            "branch_address": "京都市下京区高辻通...",
            "industry_type": "マンション",
            "average_volume": "10m3/月",
            "collection_general": "週3回",
            "collection_recycle": "週1回",
            "collection_plastic": "週1回",
            "collection_paper": "月2回",
            "business_hours": "管理人 9:00-17:00",
            "regular_holiday": "日曜日",
            "collection_start_date": "2024-01-01",
            "payment_method": "振込",
            "billing_address": "同上",
            "billing_email": "",
            "billing_contact": "鈴木 理事長",
            "pricing_list": [
                {"item": "一般ごみ（可燃）", "price": "50", "unit": "kg"},
                {"item": "不燃ごみ", "price": "70", "unit": "kg"},
                {"item": "粗大ごみ（持込）", "price": "3000", "unit": "立米"}
            ]
        }
    }
]

for sc in sample_customers:
    cust = Customer(
        company_id=company_id,
        name=sc["name"],
        address=sc["address"],
        phone=sc["phone"],
        email=sc["email"],
        contact_person=sc["contact_person"],
        contract_type=sc["contract_type"],
        contract_expiry_date=sc["contract_expiry_date"],
        billing_closing_day=sc["billing_closing_day"],
        payment_due_month_offset=sc["payment_due_month_offset"],
        payment_due_day=sc["payment_due_day"],
        form_data=json.dumps(sc["form_data"], ensure_ascii=False)
    )
    db.add(cust)

db.commit()
print("Sample customers seeded successfully!")
