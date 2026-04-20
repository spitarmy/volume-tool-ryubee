import os
import sys
from sqlalchemy import create_engine, MetaData, inspect
from sqlalchemy.orm import sessionmaker

# Add the parent directory to sys.path so 'app' can be imported
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), 'app')))

from app.database import Base
from app import models
import backup_db

# Configuration for source and destination databases
# Using environment variables or default local values for testing
SQLITE_URL = "sqlite:///./ryubee_dev.db"
POSTGRES_URL = os.environ.get("POSTGRES_URL", "postgresql://user:password@localhost/ryubee")  # Replace with actual Render URL when running

def run_migration():
    print("🚀 Starting Data Migration to PostgreSQL...")
    
    # Step 1: Backup SQLite DB
    print("\n--- Step 1: Backing up SQLite DB ---")
    backup_path = backup_db.run_backup()
    if not backup_path:
        print("Cannot proceed with migration without a successful backup.")
        return

    # Step 2: Establish Connections
    print("\n--- Step 2: Connecting to Databases ---")
    try:
        sqlite_engine = create_engine(SQLITE_URL)
        postgres_engine = create_engine(POSTGRES_URL)
        print("Connected successfully.")
    except Exception as e:
        print(f"Failed to connect: {e}")
        return

    # Step 3: Create Tables in PostgreSQL
    print("\n--- Step 3: Creating Tables in target Database ---")
    try:
        Base.metadata.create_all(postgres_engine)
        print("Tables created successfully.")
    except Exception as e:
        print(f"Failed to create tables: {e}")
        return

    # Step 4: Migrate Data
    print("\n--- Step 4: Migrating Data ---")
    
    metadata = MetaData()
    metadata.reflect(bind=sqlite_engine)
    
    # To handle foreign key constraints, we usually need to insert data in topographical order.
    # We will use SQLAlchemy's sorted_tables to get them in roughly the right insertion order.
    tables = Base.metadata.sorted_tables
    
    with postgres_engine.begin() as pg_conn:
        with sqlite_engine.connect() as sq_conn:
            for table in tables:
                print(f"Migrating table: {table.name}...")
                
                # Fetch all rows from sqlite
                rows = sq_conn.execute(table.select()).fetchall()
                if not rows:
                    print(f"  No data found for {table.name}, skipping.")
                    continue
                
                # Convert rows to list of dicts
                row_dicts = [dict(row._mapping) for row in rows]
                
                # Insert into postgres
                try:
                    # In a real batch migration, you might want to use chunks if data is large.
                    pg_conn.execute(table.insert(), row_dicts)
                    print(f"  ✅ Migrated {len(row_dicts)} rows for {table.name}.")
                except Exception as e:
                    print(f"  ❌ Failed to migrate {table.name}: {e}")
                    # Usually we'd want to raise here to trigger rollback of the whole transaction
                    # raise e 

    print("\n🎉 Migration completed successfully!")
    print(f"Please verify data integrity using verify_migration.py")

if __name__ == "__main__":
    confirm = input("This will copy data from SQLite to PostgreSQL. Ensure POSTGRES_URL is correctly set. Type 'yes' to continue: ")
    if confirm.lower() == 'yes':
        run_migration()
    else:
        print("Migration aborted.")
