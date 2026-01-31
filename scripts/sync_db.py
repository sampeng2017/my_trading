#!/usr/bin/env python3
"""
Sync database between Turso cloud and local SQLite.

Usage:
    python scripts/sync_db.py --backup   # Cloud → Local (backup)
    python scripts/sync_db.py --restore  # Local → Cloud (restore)
"""
import os
import sys
import sqlite3
import argparse
import logging
from dotenv import load_dotenv

# Add project root to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Initialize logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Load env variables
load_dotenv()

LOCAL_DB_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'data', 'agent.db')
TURSO_URL = os.environ.get('TURSO_DATABASE_URL')
TURSO_TOKEN = os.environ.get('TURSO_AUTH_TOKEN')


def get_turso_connection():
    """Connect to Turso cloud database."""
    try:
        import libsql_experimental as libsql
        return libsql.connect(TURSO_URL, auth_token=TURSO_TOKEN)
    except ImportError:
        logger.error("libsql-experimental not installed. Run: pip install libsql-experimental")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Failed to connect to Turso: {e}")
        sys.exit(1)


def get_local_connection():
    """Connect to local SQLite database."""
    try:
        return sqlite3.connect(LOCAL_DB_PATH)
    except Exception as e:
        logger.error(f"Failed to connect to local DB: {e}")
        sys.exit(1)


def get_tables(conn):
    """Get list of user tables from database."""
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")
    return [row[0] for row in cursor.fetchall()]


def sync_table(source_conn, target_conn, table_name):
    """Sync a single table from source to target (replace mode)."""
    source_cursor = source_conn.cursor()
    target_cursor = target_conn.cursor()

    # Get data from source
    source_cursor.execute(f"SELECT * FROM {table_name}")
    rows = source_cursor.fetchall()

    # Clear target table
    try:
        target_cursor.execute(f"DELETE FROM {table_name}")
    except Exception as e:
        logger.warning(f"  Could not clear {table_name}: {e}")
        return 0

    # Insert data into target
    if rows:
        col_count = len(rows[0])
        placeholders = ', '.join(['?'] * col_count)
        insert_sql = f"INSERT INTO {table_name} VALUES ({placeholders})"

        try:
            target_cursor.executemany(insert_sql, rows)
        except Exception as e:
            logger.error(f"  Failed to insert into {table_name}: {e}")
            return 0

    return len(rows)


def backup():
    """Sync from Turso cloud to local SQLite (backup)."""
    if not TURSO_URL or not TURSO_TOKEN:
        logger.error("Turso credentials not set. Check TURSO_DATABASE_URL and TURSO_AUTH_TOKEN in .env")
        return False

    logger.info("=" * 50)
    logger.info("BACKUP: Turso Cloud → Local SQLite")
    logger.info("=" * 50)
    logger.info(f"Source: {TURSO_URL[:40]}...")
    logger.info(f"Target: {LOCAL_DB_PATH}")
    logger.info("")

    turso_conn = get_turso_connection()
    local_conn = get_local_connection()

    try:
        tables = get_tables(turso_conn)
        total_rows = 0

        for table in tables:
            rows = sync_table(turso_conn, local_conn, table)
            logger.info(f"  {table}: {rows} rows")
            total_rows += rows

        local_conn.commit()
        logger.info("")
        logger.info(f"Backup complete: {len(tables)} tables, {total_rows} total rows")
        return True

    except Exception as e:
        logger.error(f"Backup failed: {e}")
        return False
    finally:
        turso_conn.close()
        local_conn.close()


def restore():
    """Sync from local SQLite to Turso cloud (restore)."""
    if not os.path.exists(LOCAL_DB_PATH):
        logger.error(f"Local database not found: {LOCAL_DB_PATH}")
        return False

    if not TURSO_URL or not TURSO_TOKEN:
        logger.error("Turso credentials not set. Check TURSO_DATABASE_URL and TURSO_AUTH_TOKEN in .env")
        return False

    logger.info("=" * 50)
    logger.info("RESTORE: Local SQLite → Turso Cloud")
    logger.info("=" * 50)
    logger.info(f"Source: {LOCAL_DB_PATH}")
    logger.info(f"Target: {TURSO_URL[:40]}...")
    logger.info("")

    local_conn = get_local_connection()
    turso_conn = get_turso_connection()

    try:
        tables = get_tables(local_conn)
        total_rows = 0

        for table in tables:
            rows = sync_table(local_conn, turso_conn, table)
            logger.info(f"  {table}: {rows} rows")
            total_rows += rows

        turso_conn.commit()
        logger.info("")
        logger.info(f"Restore complete: {len(tables)} tables, {total_rows} total rows")
        return True

    except Exception as e:
        logger.error(f"Restore failed: {e}")
        return False
    finally:
        local_conn.close()
        turso_conn.close()


def main():
    parser = argparse.ArgumentParser(
        description="Sync database between Turso cloud and local SQLite"
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--backup', action='store_true',
                       help='Backup: Cloud → Local')
    group.add_argument('--restore', action='store_true',
                       help='Restore: Local → Cloud')

    args = parser.parse_args()

    if args.backup:
        success = backup()
    else:
        success = restore()

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
