"""company_logo, company_stamp カラムを CompanySettings に追加するマイグレーション"""
import os, sys
sys.path.insert(0, os.path.dirname(__file__))

from sqlalchemy import text
from app.database import engine

DDL = [
    "ALTER TABLE company_settings ADD COLUMN IF NOT EXISTS company_logo TEXT DEFAULT ''",
    "ALTER TABLE company_settings ADD COLUMN IF NOT EXISTS company_stamp TEXT DEFAULT ''",
]

def run():
    with engine.connect() as conn:
        for stmt in DDL:
            try:
                conn.execute(text(stmt))
                print(f"OK: {stmt[:60]}...")
            except Exception as e:
                print(f"SKIP: {e}")
        conn.commit()
    print("Migration complete.")

if __name__ == "__main__":
    run()
