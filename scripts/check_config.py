#!/usr/bin/env python3
"""
Check Configuration Status

Verifies that API keys and environment variables are properly set.
Usage: python scripts/check_config.py
"""

import os
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root / "src"))


def check_env_var(name: str, required: bool = False, fallback_msg: str = "") -> bool:
    """Check if environment variable is set."""
    value = os.getenv(name)
    if value:
        # Mask the key for security
        masked = value[:4] + "..." + value[-4:] if len(value) > 10 else "***"
        print(f"  {name}: ✅ Set ({masked})")
        return True
    else:
        status = "❌ Not set" if required else "⚪ Not set"
        msg = f" - {fallback_msg}" if fallback_msg else ""
        print(f"  {name}: {status}{msg}")
        return False


def main():
    print("=" * 60)
    print("Configuration Status Check")
    print("=" * 60)

    # Check API Keys
    print("\n📡 API Keys:")
    gemini_ok = check_env_var("GEMINI_API_KEY", required=True, fallback_msg="Required for AI")
    check_env_var("ALPACA_API_KEY", fallback_msg="Will use Yahoo Finance")
    check_env_var("ALPACA_SECRET_KEY", fallback_msg="Required with ALPACA_API_KEY")
    check_env_var("ALPHA_VANTAGE_API_KEY", fallback_msg="Backup for screener")
    check_env_var("FINNHUB_API_KEY", fallback_msg="No news analysis")

    # Check Notification Config
    print("\n📧 Notifications:")
    check_env_var("GMAIL_USER", fallback_msg="No email alerts")
    check_env_var("GMAIL_APP_PASSWORD", fallback_msg="Required with GMAIL_USER")
    check_env_var("EMAIL_RECIPIENT", fallback_msg="Required with GMAIL_USER")
    check_env_var("IMESSAGE_RECIPIENT", fallback_msg="No iMessage alerts")

    # Check config file
    print("\n📄 Config File:")
    config_path = project_root / "config" / "config.yaml"
    if config_path.exists():
        print(f"  config/config.yaml: ✅ Found")
    else:
        print(f"  config/config.yaml: ❌ Not found")

    # Check database
    print("\n🗄️  Database:")
    db_path = project_root / "data" / "agent.db"
    if db_path.exists():
        size = db_path.stat().st_size
        print(f"  data/agent.db: ✅ Found ({size:,} bytes)")
    else:
        print(f"  data/agent.db: ⚪ Not initialized")
        print(f"     Run: sqlite3 data/agent.db < data/init_schema.sql")

    # Check inbox folder
    print("\n📥 Inbox Folder:")
    inbox_path = project_root / "inbox"
    if inbox_path.exists():
        csv_files = list(inbox_path.glob("*.csv"))
        print(f"  inbox/: ✅ Found ({len(csv_files)} CSV files)")
        for f in csv_files[:3]:
            print(f"     - {f.name}")
        if len(csv_files) > 3:
            print(f"     ... and {len(csv_files) - 3} more")
    else:
        print(f"  inbox/: ⚪ Not found")

    # Summary
    print("\n" + "=" * 60)
    if gemini_ok:
        print("✅ Minimum configuration met (Gemini API key set)")
        print("   Run: python src/main_orchestrator.py --mode premarket")
    else:
        print("❌ Missing required configuration")
        print("   Set GEMINI_API_KEY in .env file, then run: source .env")
    print("=" * 60)

    return 0 if gemini_ok else 1


if __name__ == "__main__":
    sys.exit(main())
