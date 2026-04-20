from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.models import Customer, User
import os
from dotenv import load_dotenv

load_dotenv()
SQLALCHEMY_DATABASE_URL = os.getenv("DATABASE_URL").replace("postgres://", "postgresql://", 1)
engine = create_engine(SQLALCHEMY_DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
db = SessionLocal()

users = db.query(User).all()
print("Users:")
for u in users:
    print(f"User ID: {u.id}, Email: {u.email}, Company ID: {u.company_id}")

customers = db.query(Customer).all()
print("\nCustomers:")
for c in customers:
    print(f"Customer Name: {c.name}, Company ID: {c.company_id}")
