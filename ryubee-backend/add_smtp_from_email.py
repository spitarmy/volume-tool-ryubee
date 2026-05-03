import os
import sqlite3
import psycopg2
from urllib.parse import urlparse
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./ryubee_dev.db")

def upgrade_sqlite(db_path):
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    try:
        cur.execute("ALTER TABLE company_settings ADD COLUMN smtp_from_email VARCHAR(255) DEFAULT ''")
        print("Successfully added smtp_from_email to SQLite.")
    except sqlite3.OperationalError as e:
        print(f"Skipped, might already exist: {e}")
    conn.commit()
    conn.close()

def upgrade_postgres(url):
    parsed = urlparse(url)
    conn = psycopg2.connect(
        dbname=parsed.path[1:],
        user=parsed.username,
        password=parsed.password,
        host=parsed.hostname,
        port=parsed.port
    )
    cur = conn.cursor()
    try:
        cur.execute("ALTER TABLE company_settings ADD COLUMN smtp_from_email VARCHAR(255) DEFAULT ''")
        print("Successfully added smtp_from_email to PostgreSQL.")
    except psycopg2.errors.DuplicateColumn:
        print("Skipped, column already exists in PostgreSQL.")
    except Exception as e:
        print(f"Error: {e}")
    conn.commit()
    conn.close()

if __name__ == "__main__":
    if DATABASE_URL.startswith("sqlite"):
        db_path = DATABASE_URL.replace("sqlite:///", "")
        upgrade_sqlite(db_path)
    elif DATABASE_URL.startswith("postgres"):
        upgrade_postgres(DATABASE_URL)
    else:
        print(f"Unknown DB type: {DATABASE_URL}")
