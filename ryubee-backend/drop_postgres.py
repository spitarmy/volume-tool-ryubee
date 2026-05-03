import os
import sys
import sqlalchemy
from sqlalchemy import create_engine
from app.database import Base
from app import models

POSTGRES_URL = os.environ.get("POSTGRES_URL")

def main():
    if not POSTGRES_URL:
        print("Set POSTGRES_URL")
        return
    engine = create_engine(POSTGRES_URL)
    print("Dropping all tables...")
    Base.metadata.drop_all(engine)
    print("All tables dropped from Postgres!")

if __name__ == "__main__":
    main()
