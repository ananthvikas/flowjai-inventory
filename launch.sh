#!/bin/bash
# flowjAI Inventory Manager - Standalone launcher (macOS / Linux)
clear
echo ""
echo " =========================================="
echo "   flowjAI Inventory Manager - Starting"
echo " =========================================="
echo ""

cd "$(dirname "$0")"

# Check Python
if ! command -v python3 &>/dev/null; then
    echo " ERROR: Python 3 is not installed."
    if [[ "$OSTYPE" == "darwin"* ]]; then
        echo " Install: brew install python@3.11"
        echo " Or download from https://www.python.org/downloads/"
    else
        echo " Install: sudo apt install python3 python3-venv"
    fi
    read -p " Press Enter to close..."
    exit 1
fi

# Create venv on first run
if [ ! -f "venv/bin/activate" ]; then
    echo " First run - setting up environment (takes 2-3 minutes)..."
    python3 -m venv venv
fi

source venv/bin/activate

# Install dependencies
echo " Checking dependencies..."
if [ -d "wheels" ] && [ "$(ls -A wheels 2>/dev/null)" ]; then
    pip install --quiet --no-index --find-links=wheels \
        -r backend/requirements.txt 2>/dev/null || \
    pip install --quiet -r backend/requirements.txt
else
    pip install --quiet -r backend/requirements.txt
fi || { echo " ERROR: failed to install required packages."; read -p " Press Enter to close..."; exit 1; }

mkdir -p data/logs

# Show network address
if [[ "$OSTYPE" == "darwin"* ]]; then
    IP=$(ipconfig getifaddr en0 2>/dev/null || ipconfig getifaddr en1 2>/dev/null)
else
    IP=$(hostname -I 2>/dev/null | awk '{print $1}')
fi
echo ""
echo " =========================================="
echo "   On this computer:     http://localhost:8000"
[ -n "$IP" ] && echo "   From other computers: http://$IP:8000"
echo " =========================================="
echo ""
echo " First run: the browser opens a setup page to create your admin account."
echo " Do not close this window while the app is running."
echo ""

# run.py does the rest, exactly as the packaged app does: creates the schema on a
# fresh install (or applies pending upgrades, refusing to start if one fails),
# never loads demo data, opens the browser, and listens on the LAN (--lan).
python3 run.py --lan
