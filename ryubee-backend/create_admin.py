import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app import models, auth

def create_user():
    db_url = os.environ.get("POSTGRES_URL")
    engine = create_engine(db_url)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    db = SessionLocal()

    # Find the company_id (assuming only one main company exists right now)
    company = db.query(models.Company).first()
    if not company:
        print("Company not found!")
        return

    email = "koji.yamabun@outlook.jp"
    password = "koji0321"

    existing_user = db.query(models.User).filter_by(email=email).first()
    if existing_user:
        print(f"User {email} already exists! Promoting to admin if not already.")
        existing_user.role = "admin"
        db.commit()
        return

    new_user = models.User(
        company_id=company.id,
        email=email,
        password_hash=auth.hash_password(password),
        name="Koji Yamabun",
        role="admin"
    )
    db.add(new_user)
    db.commit()
    print(f"User {email} created successfully as admin!")

if __name__ == "__main__":
    create_user()
