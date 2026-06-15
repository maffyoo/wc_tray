#!/bin/bash
# Installs the daily sync as a launchd agent (runs at 6am every day).
set -e
DIR="$(cd "$(dirname "$0")" && pwd)"
PLIST="$HOME/Library/LaunchAgents/com.wctray.sync.plist"

# Substitute the real script dir into the plist
sed "s|SCRIPT_DIR|$DIR|g" "$DIR/com.wctray.sync.plist" > "$PLIST"

# Unload first in case it was previously installed
launchctl unload "$PLIST" 2>/dev/null || true
launchctl load "$PLIST"

echo "Installed. Daily sync will run at 06:00."
echo "To run the sync right now: $DIR/sync_now.sh"
