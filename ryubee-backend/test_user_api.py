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

bad_customers = db.query(Customer).filter(
    (Customer.name == None) | 
    (Customer.address == None) | 
    (Customer.phone == None) | 
    (Customer.email == None) | 
    (Customer.contact_person == None) | 
    (Customer.notes == None)
).all()

print("Found", len(bad_customers), "customers with NULL fields that CustomerOut expects to be non-null")
for c in bad_customers:
    print(f"ID: {c.id[:8]}, Name: {c.name}")
