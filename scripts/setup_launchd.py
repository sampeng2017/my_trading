#!/usr/bin/env python3
"""
Setup launchd for automatic scheduling.

This script:
1. Reads API keys from .env file
2. Creates a personalized launchd plist with actual values
3. Installs it to ~/Library/LaunchAgents/
4. Loads the schedule

Usage:
    python scripts/setup_launchd.py          # Install and load
    python scripts/setup_launchd.py --remove # Uninstall
"""

import os
import sys
import shutil
import subprocess
from pathlib import Path

# Paths
PROJECT_ROOT = Path(__file__).parent.parent
ENV_FILE = PROJECT_ROOT / ".env"
PLIST_TEMPLATE = PROJECT_ROOT / "launchd" / "com.shengpeng.stockagent.plist"
PLIST_DEST = Path.home() / "Library" / "LaunchAgents" / "com.shengpeng.stockagent.plist"
LABEL = "com.shengpeng.stockagent"


def load_env():
    """Load environment variables from .env file."""
    env_vars = {}
    if ENV_FILE.exists():
        with open(ENV_FILE) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    # Handle export VAR=value or VAR=value
                    if line.startswith('export '):
                        line = line[7:]
                    key, _, value = line.partition('=')
                    # Remove quotes
                    value = value.strip().strip('"').strip("'")
                    env_vars[key.strip()] = value
    return env_vars


def create_plist_with_keys(env_vars):
    """Create plist with actual API key values."""
    plist_content = f'''<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
"http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>{LABEL}</string>

    <key>ProgramArguments</key>
    <array>
        <string>{PROJECT_ROOT}/venv/bin/python3</string>
        <string>{PROJECT_ROOT}/src/main_orchestrator.py</string>
    </array>

    <key>EnvironmentVariables</key>
    <dict>
        <key>PYTHONPATH</key>
        <string>{PROJECT_ROOT}</string>
        <key>PATH</key>
        <string>/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin</string>

        <key>ALPACA_API_KEY</key>
        <string>{env_vars.get('ALPACA_API_KEY', '')}</string>
        <key>ALPACA_SECRET_KEY</key>
        <string>{env_vars.get('ALPACA_SECRET_KEY', '')}</string>
        <key>GEMINI_API_KEY</key>
        <string>{env_vars.get('GEMINI_API_KEY', '')}</string>
        <key>FINNHUB_API_KEY</key>
        <string>{env_vars.get('FINNHUB_API_KEY', '')}</string>
        <key>ALPHA_VANTAGE_API_KEY</key>
        <string>{env_vars.get('ALPHA_VANTAGE_API_KEY', '')}</string>

        <key>IMESSAGE_RECIPIENT</key>
        <string>{env_vars.get('IMESSAGE_RECIPIENT', '')}</string>
        <key>GMAIL_USER</key>
        <string>{env_vars.get('GMAIL_USER', '')}</string>
        <key>GMAIL_APP_PASSWORD</key>
        <string>{env_vars.get('GMAIL_APP_PASSWORD', '')}</string>
        <key>EMAIL_RECIPIENT</key>
        <string>{env_vars.get('EMAIL_RECIPIENT', '')}</string>
    </dict>

    <key>StandardOutPath</key>
    <string>{PROJECT_ROOT}/logs/stdout.log</string>
    <key>StandardErrorPath</key>
    <string>{PROJECT_ROOT}/logs/stderr.log</string>

    <!-- Schedule (Pacific Time) -->
    <key>StartCalendarInterval</key>
    <array>
        <!-- 6:00 AM - Pre-market scan -->
        <dict>
            <key>Hour</key><integer>6</integer>
            <key>Minute</key><integer>0</integer>
        </dict>
        <!-- 6:35 AM - Market open -->
        <dict>
            <key>Hour</key><integer>6</integer>
            <key>Minute</key><integer>35</integer>
        </dict>
        <!-- 9:00 AM - Mid-morning -->
        <dict>
            <key>Hour</key><integer>9</integer>
            <key>Minute</key><integer>0</integer>
        </dict>
        <!-- 11:00 AM - Mid-day -->
        <dict>
            <key>Hour</key><integer>11</integer>
            <key>Minute</key><integer>0</integer>
        </dict>
        <!-- 1:05 PM - Post-market -->
        <dict>
            <key>Hour</key><integer>13</integer>
            <key>Minute</key><integer>5</integer>
        </dict>
    </array>

    <key>WorkingDirectory</key>
    <string>{PROJECT_ROOT}</string>

    <key>RunAtLoad</key>
    <false/>

    <key>KeepAlive</key>
    <false/>
</dict>
</plist>
'''
    return plist_content


def install():
    """Install and load the launchd job."""
    print("=" * 60)
    print("Setting up Automatic Scheduling")
    print("=" * 60)

    # Load environment
    print("\n📄 Loading .env file...")
    env_vars = load_env()

    if not env_vars.get('GEMINI_API_KEY'):
        print("⚠️  Warning: GEMINI_API_KEY not found in .env")

    # Create logs directory
    logs_dir = PROJECT_ROOT / "logs"
    logs_dir.mkdir(exist_ok=True)

    # Unload existing if present
    print("\n🔄 Checking for existing schedule...")
    subprocess.run(
        ["launchctl", "unload", str(PLIST_DEST)],
        capture_output=True
    )

    # Create plist with actual values
    print("📝 Creating launchd configuration...")
    plist_content = create_plist_with_keys(env_vars)

    # Write to destination
    PLIST_DEST.parent.mkdir(parents=True, exist_ok=True)
    with open(PLIST_DEST, 'w') as f:
        f.write(plist_content)

    print(f"   Saved to: {PLIST_DEST}")

    # Load the job
    print("\n🚀 Loading schedule...")
    result = subprocess.run(
        ["launchctl", "load", str(PLIST_DEST)],
        capture_output=True,
        text=True
    )

    if result.returncode != 0:
        print(f"❌ Error: {result.stderr}")
        return False

    # Verify
    print("\n✅ Schedule installed successfully!")
    print("\n" + "=" * 60)
    print("AUTOMATIC SCHEDULE (Pacific Time)")
    print("=" * 60)
    print("  6:00 AM  - Pre-market scan (news, screening)")
    print("  6:35 AM  - Market open (recommendations)")
    print("  9:00 AM  - Mid-morning check")
    print(" 11:00 AM  - Mid-day check")
    print("  1:05 PM  - Post-market summary")
    print("=" * 60)

    print("\n📱 You'll receive iMessage alerts when trades are recommended.")
    print("📧 Daily summary emails sent after market close.")

    print("\n💡 Commands:")
    print("   Check status:  launchctl list | grep stockagent")
    print("   View logs:     tail -f logs/stdout.log")
    print("   Remove:        python scripts/setup_launchd.py --remove")

    return True


def remove():
    """Unload and remove the launchd job."""
    print("Removing automatic schedule...")

    # Unload
    subprocess.run(
        ["launchctl", "unload", str(PLIST_DEST)],
        capture_output=True
    )

    # Remove file
    if PLIST_DEST.exists():
        PLIST_DEST.unlink()
        print(f"✅ Removed: {PLIST_DEST}")
    else:
        print("ℹ️  No schedule was installed.")

    print("\n💡 You can still run manually:")
    print("   python scripts/run_system.py market")


def main():
    if len(sys.argv) > 1 and sys.argv[1] == '--remove':
        remove()
    else:
        install()


if __name__ == "__main__":
    main()
