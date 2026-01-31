"""
Migrate local SQLite database to Turso Cloud.

Usage:
    python scripts/migrate_to_turso.py
"""
import os
import sqlite3
import logging
import sys
from dotenv import load_dotenv

# Add project root to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Initialize logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Load env variables
load_dotenv()

LOCAL_DB_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'data', 'agent.db')
TURSO_URL = os.environ.get('TURSO_DATABASE_URL')
TURSO_TOKEN = os.environ.get('TURSO_AUTH_TOKEN')

def migrate():
    # Validation
    if not os.path.exists(LOCAL_DB_PATH):
        logger.error(f"Local database not found at {LOCAL_DB_PATH}")
        return

    if not TURSO_URL or not TURSO_TOKEN:
        logger.error("Turso credentials not found. Please set TURSO_DATABASE_URL and TURSO_AUTH_TOKEN in .env")
        return

    logger.info("Starting migration...")
    logger.info(f"Local DB: {LOCAL_DB_PATH}")
    logger.info(f"Turso URL: {TURSO_URL}")

    # Connect to Local
    try:
        local_conn = sqlite3.connect(LOCAL_DB_PATH)
        local_cursor = local_conn.cursor()
    except Exception as e:
        logger.error(f"Failed to connect to local DB: {e}")
        return

    # Connect to Turso
    try:
        import libsql_experimental as libsql
        turso_conn = libsql.connect(TURSO_URL, auth_token=TURSO_TOKEN)
    except ImportError:
        logger.error("libsql-experimental not installed. Run: pip install libsql-experimental")
        return
    except Exception as e:
        logger.error(f"Failed to connect to Turso: {e}")
        return

    try:
        # Get list of tables from local
        local_cursor.execute("SELECT name, sql FROM sqlite_master WHERE type='table';")
        tables = local_cursor.fetchall()

        for table_name, schema_sql in tables:
            if table_name.startswith('sqlite_'): 
                continue
                
            logger.info(f"Migrating table: {table_name}")
            
            # 1. Create table
            try:
                turso_conn.execute(schema_sql)
            except Exception as e:
                logger.warning(f"  -> Table creation note: {e}")

            # 2. Copy data
            local_cursor.execute(f"SELECT * FROM {table_name}")
            rows = local_cursor.fetchall()
            
            if rows:
                col_count = len(rows[0])
                placeholders = ', '.join(['?'] * col_count)
                insert_sql = f"INSERT OR REPLACE INTO {table_name} VALUES ({placeholders})"
                
                try:
                    turso_conn.executemany(insert_sql, rows)
                    turso_conn.commit()
                    logger.info(f"  -> Migrated {len(rows)} rows")
                except Exception as e:
                    logger.error(f"  -> Failed to migrate data: {e}")
            else:
                logger.info("  -> Table is empty")

    except Exception as e:
        logger.error(f"Migration failed during execution: {e}")
    finally:
        local_conn.close()
        turso_conn.close()
        logger.info("Migration finished.")

if __name__ == "__main__":
    migrate()
