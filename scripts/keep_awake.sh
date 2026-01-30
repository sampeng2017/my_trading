#!/bin/bash
# Keep Mac awake during market hours (6 AM - 2 PM PT)
# Run with: nohup ./scripts/keep_awake.sh &

# caffeinate -i prevents idle sleep
# -t 28800 = 8 hours (6 AM to 2 PM)

echo "Keeping Mac awake for 8 hours (market hours)..."
caffeinate -i -t 28800
echo "Caffeinate ended. Mac can sleep now."
