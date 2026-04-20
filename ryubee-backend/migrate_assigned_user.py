import os
import sys

# Add the parent directory to sys.path so 'app' can be imported
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), 'app')))

from app.database import engine
from sqlalchemy import text

def run_migration():
    print("Starting database migration to add assigned_user_id to customers...")
    try:
        with engine.begin() as conn:
            try:
                conn.execute(text("ALTER TABLE customers ADD COLUMN assigned_user_id VARCHAR;"))
                print("Added column assigned_user_id to customers.")
            except Exception as e:
                print(f"Column in customers might already exist or error occurred: {e}")
                
        print("Migration completed successfully.")
    except Exception as e:
        print(f"Migration failed: {e}")

if __name__ == "__main__":
    run_migration()
