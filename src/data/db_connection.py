"""
Database connection adapter supporting both local SQLite and Turso cloud.

Environment variables are read at call time (not import time) so changes
take effect without restarting the process.
"""
import os
import sqlite3
import time
from contextlib import contextmanager
from typing import Generator, Any

try:
    from dotenv import load_dotenv
    # Load .env explicitly for cases where it wasn't loaded by main
    load_dotenv()
except ImportError:
    pass

def _get_db_config():
    """Read database config from environment at call time."""
    return {
        'mode': os.environ.get('DB_MODE', 'local'),
        'turso_url': os.environ.get('TURSO_DATABASE_URL', ''),
        'turso_token': os.environ.get('TURSO_AUTH_TOKEN', ''),
    }


@contextmanager
def get_connection(db_path: str = None) -> Generator[Any, None, None]:
    """
    Get database connection based on DB_MODE environment variable.

    Args:
        db_path: Path to local SQLite database (used when DB_MODE='local')

    Yields:
        Database connection object (sqlite3.Connection or libsql Connection)
    """
    config = _get_db_config()

    if config['mode'] == 'turso' and config['turso_url']:
        import libsql_experimental as libsql
        # For Turso, we use the specific URL and token
        conn = libsql.connect(config['turso_url'], auth_token=config['turso_token'])
    else:
        # Fallback to local SQLite
        if not db_path:
             # Try to find a default if not provided
            project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            db_path = os.path.join(project_root, 'data', 'agent.db')
            
        conn = sqlite3.connect(db_path)

    try:
        yield conn
    finally:
        conn.close()


def get_db_mode() -> str:
    """Return current database mode."""
    return _get_db_config()['mode']
