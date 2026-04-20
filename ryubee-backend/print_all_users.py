from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.models import User
import os
from dotenv import load_dotenv

load_dotenv()
SQLALCHEMY_DATABASE_URL = os.getenv("DATABASE_URL").replace("postgres://", "postgresql://", 1)
engine = create_engine(SQLALCHEMY_DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
db = SessionLocal()

users = db.query(User).all()
for u in users:
    print(f"User Email: {u.email}, Company ID: {u.company_id}")
