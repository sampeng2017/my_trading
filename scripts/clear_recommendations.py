
"""
Clear previous strategy recommendations.
Useful when algorithm logic changes and old recommendations are invalid.
"""
import os
import sys

# Add project root to path for imports
sys.path.insert(0, os.getcwd())

from src.data.db_connection import get_connection
from src.utils.config import get_db_path

def clear_recommendations():
    """Delete all rows from strategy_recommendations table."""
    db_path = get_db_path()
    print(f"Connecting to database at: {db_path}")
    
    try:
        with get_connection(db_path) as conn:
            cursor = conn.cursor()
            
            # Count before
            cursor.execute("SELECT COUNT(*) FROM strategy_recommendations")
            count_before = cursor.fetchone()[0]
            
            # Delete
            cursor.execute("DELETE FROM strategy_recommendations")
            
            # Count after
            cursor.execute("SELECT COUNT(*) FROM strategy_recommendations")
            count_after = cursor.fetchone()[0]
            
            conn.commit()
            
            print(f"Deleted {count_before} recommendations.")
            print(f"Remaining: {count_after}")
            
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    confirm = input("are you sure? (Y/n): ")
    if confirm == 'Y':
        clear_recommendations()
    else:
        print("Operation cancelled.")
