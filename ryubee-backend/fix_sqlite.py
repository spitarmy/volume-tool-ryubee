import sqlite3
from app.database import engine, Base
from app import models

conn = sqlite3.connect('ryubee_dev.db')
cursor = conn.cursor()

# Get all tables from SQLAlchemy
for table_name, table in Base.metadata.tables.items():
    if table_name == 'alembic_version': continue
    
    # Get columns from sqlite
    try:
        cursor.execute(f"PRAGMA table_info({table_name})")
        existing_cols = {row[1] for row in cursor.fetchall()}
    except Exception:
        continue
        
    for column in table.columns:
        if column.name not in existing_cols:
            col_type = "TEXT"
            if str(column.type) == "INTEGER": col_type = "INTEGER"
            elif str(column.type) == "BOOLEAN": col_type = "BOOLEAN"
            
            try:
                print(f"Adding {column.name} to {table_name}...")
                cursor.execute(f"ALTER TABLE {table_name} ADD COLUMN {column.name} {col_type}")
            except Exception as e:
                print(f"Failed to add {column.name}: {e}")

conn.commit()
conn.close()
print("Done fixing sqlite!")
