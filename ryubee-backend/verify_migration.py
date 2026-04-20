import os
import sys
from sqlalchemy import create_engine, MetaData
from sqlalchemy.orm import sessionmaker

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), 'app')))

from app.database import Base

SQLITE_URL = "sqlite:///./ryubee_dev.db"
POSTGRES_URL = os.environ.get("POSTGRES_URL", "postgresql://user:password@localhost/ryubee") 

def verify():
    print("🔍 Starting Verification Process...")
    try:
        sqlite_engine = create_engine(SQLITE_URL)
        postgres_engine = create_engine(POSTGRES_URL)
    except Exception as e:
        print(f"Connection failed: {e}")
        return

    tables = Base.metadata.sorted_tables
    
    all_match = True
    
    for table in tables:
        with sqlite_engine.connect() as sq_conn, postgres_engine.connect() as pg_conn:
            # Count rows in SQLite
            sq_count = sq_conn.execute(table.count()).scalar()
            
            # Count rows in PostgreSQL
            try:
                pg_count = pg_conn.execute(table.count()).scalar()
            except Exception as e:
                 print(f"Error reading {table.name} in PostgreSQL: {e}")
                 all_match = False
                 continue
                 
            if sq_count == pg_count:
                print(f"✅ {table.name}: {sq_count} == {pg_count} (MATCH)")
            else:
                print(f"❌ {table.name}: {sq_count} != {pg_count} (MISMATCH)")
                all_match = False
                
    if all_match:
        print("\n🎉 All tables match perfectly! Migration is safe.")
    else:
        print("\n⚠️ Data mismatches found. Please investigate before switching over.")

if __name__ == "__main__":
    verify()
