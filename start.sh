#!/usr/bin/env bash
set -e

echo "========================================================"
echo "  Discord Music Bot + Web UI Launcher (Linux)"
echo "========================================================"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# 1. Setup Python Virtual Environment
if [ ! -d "venv" ]; then
    echo "[*] Creating Python virtual environment (venv)..."
    python3 -m venv venv
    source venv/bin/activate
    pip install --upgrade pip
    pip install -r requirements.txt
else
    source venv/bin/activate
fi

# 2. Setup Web UI Dependencies
if [ -d "web" ] && [ ! -d "web/node_modules" ]; then
    echo "[*] Installing Web UI npm dependencies..."
    (cd web && npm install)
fi

# 3. Create config files from examples if missing
if [ ! -f "config.txt" ] && [ -f "config.example.txt" ]; then
    cp config.example.txt config.txt
    echo "[!] Created config.txt from template. Please configure BOT_TOKEN!"
fi

if [ -d "web" ] && [ ! -f "web/.env" ] && [ -f "web/.env.example" ]; then
    cp web/.env.example web/.env
    echo "[!] Created web/.env from template. Please configure DISCORD_CLIENT_ID!"
fi

# 4. Launch Web UI in background if present
WEB_PID=""
if [ -d "web" ]; then
    echo "[*] Starting Web UI on port 5000..."
    (cd web && npm start) &
    WEB_PID=$!
fi

cleanup() {
    if [ -n "$WEB_PID" ]; then
        echo "[*] Stopping Web UI process (PID: $WEB_PID)..."
        kill "$WEB_PID" 2>/dev/null || true
    fi
}
trap cleanup EXIT INT TERM

# 5. Launch Python Bot
echo "[*] Starting Python Music Bot Launcher..."
python3 launcher.py

