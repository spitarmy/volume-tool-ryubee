import os
import shutil
from datetime import datetime

BACKUP_DIR = "backups"
DB_FILE = "ryubee_dev.db"

def run_backup():
    if not os.path.exists(BACKUP_DIR):
        os.makedirs(BACKUP_DIR)
        
    if not os.path.exists(DB_FILE):
        print(f"Error: Database file {DB_FILE} not found.")
        return None

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_file = os.path.join(BACKUP_DIR, f"ryubee_dev_{timestamp}.db")
    
    try:
        shutil.copy2(DB_FILE, backup_file)
        print(f"✅ Database successfully backed up to: {backup_file}")
        return backup_file
    except Exception as e:
        print(f"❌ Backup failed: {e}")
        return None

if __name__ == "__main__":
    run_backup()
