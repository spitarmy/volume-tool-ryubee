from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.models import Company, User, CompanySettings
import os

engine = create_engine(os.environ.get("POSTGRES_URL", "postgresql://user:password@localhost/ryubee"))
Session = sessionmaker(bind=engine)
db = Session()

user = db.query(User).filter_by(email="koji.yamabun@outlook.jp").first()
print("User company_id:", user.company_id)
company = db.query(Company).filter_by(id=user.company_id).first()
print("Company:", company)
settings = db.query(CompanySettings).filter_by(company_id=user.company_id).first()
print("Settings:", settings)
