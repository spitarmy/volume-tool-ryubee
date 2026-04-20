from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.models import Customer
import os
from dotenv import load_dotenv

load_dotenv()
SQLALCHEMY_DATABASE_URL = os.getenv("DATABASE_URL").replace("postgres://", "postgresql://", 1)
engine = create_engine(SQLALCHEMY_DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
db = SessionLocal()

all_c = db.query(Customer).all()
for c in all_c:
    for field in ["name", "address", "phone", "contract_type", "email", "contact_person", "notes", "contract_expiry_date", "billing_closing_day", "payment_due_month_offset", "payment_due_day", "form_data", "created_at"]:
        val = getattr(c, field)
        if val is None:
            print(f"Customer {c.id} has None in {field}")
