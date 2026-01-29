#!/usr/bin/env python3
"""
Run Trading System

Convenience wrapper to run the main orchestrator with common options.
Usage: python scripts/run_system.py [MODE]

Modes:
  premarket   - Morning scan (safe, no recommendations)
  market      - Generate trade recommendations
  postmarket  - Daily summary email
  auto        - Auto-detect based on time (default)
"""

import sys
import os
import subprocess
from pathlib import Path

project_root = Path(__file__).parent.parent


def main():
    # Determine mode
    mode = sys.argv[1] if len(sys.argv) > 1 else "auto"

    valid_modes = ["premarket", "market", "postmarket", "auto"]
    if mode not in valid_modes:
        print(f"❌ Invalid mode: {mode}")
        print(f"   Valid modes: {', '.join(valid_modes)}")
        return 1

    # Check if .env is loaded
    if not os.getenv("GEMINI_API_KEY"):
        print("⚠️  Environment variables not loaded!")
        print("   Run: source .env")
        print()

    # Build command
    orchestrator = project_root / "src" / "main_orchestrator.py"
    cmd = [sys.executable, str(orchestrator)]

    if mode != "auto":
        cmd.extend(["--mode", mode])

    print("=" * 60)
    print(f"Running Trading System - Mode: {mode.upper()}")
    print("=" * 60)
    print()

    # Run the orchestrator
    try:
        result = subprocess.run(cmd, cwd=str(project_root))
        return result.returncode
    except KeyboardInterrupt:
        print("\n\n⚠️  Interrupted by user")
        return 130


if __name__ == "__main__":
    sys.exit(main())
