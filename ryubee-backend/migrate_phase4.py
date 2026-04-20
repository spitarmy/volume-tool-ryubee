import os
import sys

# Add the parent directory to sys.path so 'app' can be imported
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), 'app')))

from app.database import engine
from sqlalchemy import text

def run_migration():
    print("Starting database migration for Phase 4 (form_data columns)...")
    try:
        with engine.begin() as conn:
            # Add form_data column to customers if it doesn't exist
            try:
                conn.execute(text("ALTER TABLE customers ADD COLUMN form_data TEXT DEFAULT '{}';"))
                print("Added column form_data to customers.")
            except Exception as e:
                print(f"Column in customers might already exist or error occurred: {e}")
                
            # Add form_data column to jobs if it doesn't exist
            try:
                conn.execute(text("ALTER TABLE jobs ADD COLUMN form_data TEXT DEFAULT '{}';"))
                print("Added column form_data to jobs.")
            except Exception as e:
                print(f"Column in jobs might already exist or error occurred: {e}")
                
        print("Migration Phase 4 completed successfully.")
    except Exception as e:
        print(f"Migration failed: {e}")

if __name__ == "__main__":
    run_migration()
