#!/usr/bin/env bash
# Start the Courtside backend reliably.
#
# Uses a venv OUTSIDE the iCloud-synced ~/Desktop (so it can't get corrupted) and
# keeps the SQLite DB in your home dir for the same reason. Binds 0.0.0.0 so the
# ESP32 node can reach it over WiFi/hotspot.
#
# First time only:
#   python3 -m venv ~/courtside_venv
#   ~/courtside_venv/bin/pip install -r backend/requirements.txt
# Then just:  bash scripts/run_backend.sh
set -euo pipefail

PROJ="$(cd "$(dirname "$0")/.." && pwd)"
VENV="$HOME/courtside_venv"
DB_URL="sqlite:///$HOME/courtside_data.db"   # absolute path, off iCloud

if [ ! -x "$VENV/bin/uvicorn" ]; then
  echo "Stable venv missing. Create it first:"
  echo "  python3 -m venv ~/courtside_venv"
  echo "  ~/courtside_venv/bin/pip install -r '$PROJ/backend/requirements.txt'"
  exit 1
fi

cd "$PROJ"
echo "Backend: http://localhost:8000   (LAN/hotspot: http://$(ipconfig getifaddr en0 2>/dev/null || echo '<your-ip>'):8000)"
DATABASE_URL="$DB_URL" exec "$VENV/bin/uvicorn" --app-dir backend app.main:app --host 0.0.0.0 --port 8000
