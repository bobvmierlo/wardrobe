#!/usr/bin/env sh
# Build the app exactly as the Docker image does — Vite output served by FastAPI
# from ./static — and run it against a throwaway database.
#
# One origin, one server: the same shape the app runs in for real. Using the
# Vite dev server instead would test a setup nobody deploys, and would hide
# anything that only goes wrong once FastAPI serves the bundle itself.
set -eu

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)
DATA=${WARDROBE_E2E_DATA:-$(mktemp -d)}

echo "e2e: building the frontend"
cd "$ROOT/frontend"
npm run build >/dev/null

echo "e2e: installing it where the backend serves it from"
rm -rf "$ROOT/backend/static"
cp -r "$ROOT/frontend/dist" "$ROOT/backend/static"

echo "e2e: starting the app on :8099 (data in $DATA)"
cd "$ROOT/backend"
export WARDROBE_DATA_DIR="$DATA"
export WARDROBE_SECRET_KEY="e2e-secret-key-long-enough-for-hs256"
export WARDROBE_ADMIN_USERNAME="admin"
export WARDROBE_ADMIN_PASSWORD="e2e-wachtwoord"
export WARDROBE_LOG_LEVEL="WARNING"
exec "${PYTHON:-python3}" -m uvicorn app.main:app --host 127.0.0.1 --port 8099
