#!/bin/bash
cd "$(dirname "$0")"
echo "Stopping flowjAI Inventory Manager..."
pkill -f "run.py --lan" 2>/dev/null
pkill -f "uvicorn app.main" 2>/dev/null
echo "Done."
