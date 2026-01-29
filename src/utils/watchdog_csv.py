"""
CSV File Watchdog

Automatically detects and imports Fidelity CSV files when dropped into inbox.
Uses the watchdog library to monitor the file system.
"""

from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
import time
from pathlib import Path
import logging
import sys

# Add src to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root / 'src'))

from agents.portfolio_accountant import PortfolioAccountant
from utils.config import load_config, get_db_path, get_inbox_path

logger = logging.getLogger(__name__)


class CSVHandler(FileSystemEventHandler):
    """Handler for CSV file creation events."""
    
    def __init__(self, db_path: str):
        """
        Initialize handler.
        
        Args:
            db_path: Path to SQLite database
        """
        self.db_path = db_path
        self.accountant = PortfolioAccountant(db_path)
        
    def on_created(self, event):
        """Handle file creation events."""
        if event.is_directory:
            return
        
        filepath = Path(event.src_path)
        
        # Check if it's a CSV file
        if filepath.suffix.lower() == '.csv':
            logger.info(f"📁 Detected new file: {filepath.name}")
            
            # Wait a moment for file to be fully written
            time.sleep(0.5)
            
            try:
                snapshot_id = self.accountant.import_fidelity_csv(str(filepath))
                logger.info(f"✅ Portfolio imported successfully. Snapshot ID: {snapshot_id}")
                
                # Optionally move file to processed folder
                self._archive_file(filepath)
                
            except Exception as e:
                logger.error(f"❌ Failed to import {filepath.name}: {e}")
    
    def _archive_file(self, filepath: Path):
        """Move processed file to archive folder."""
        archive_dir = filepath.parent / 'processed'
        archive_dir.mkdir(exist_ok=True)
        
        archive_path = archive_dir / f"{filepath.stem}_{int(time.time())}{filepath.suffix}"
        
        try:
            filepath.rename(archive_path)
            logger.info(f"📦 Archived to: {archive_path.name}")
        except Exception as e:
            logger.warning(f"Could not archive file: {e}")


def start_watchdog(inbox_path: str = None, db_path: str = None):
    """
    Start the file system watchdog.
    
    Args:
        inbox_path: Directory to watch for CSV files
        db_path: Path to SQLite database
    """
    # Load config if paths not provided
    if not inbox_path or not db_path:
        config = load_config()
        inbox_path = inbox_path or get_inbox_path(config)
        db_path = db_path or get_db_path(config)
    
    # Ensure inbox exists
    inbox_dir = Path(inbox_path)
    inbox_dir.mkdir(parents=True, exist_ok=True)
    
    event_handler = CSVHandler(db_path)
    observer = Observer()
    observer.schedule(event_handler, inbox_path, recursive=False)
    observer.start()
    
    logger.info(f"👁️ Watching for CSV files in: {inbox_path}")
    logger.info(f"📊 Database: {db_path}")
    logger.info("Press Ctrl+C to stop...")
    
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        logger.info("Stopping watchdog...")
        observer.stop()
    
    observer.join()


if __name__ == "__main__":
    # Setup logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    start_watchdog()
