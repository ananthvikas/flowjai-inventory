#!/bin/bash
cd "$(dirname "$0")"
[ -z "$1" ] && echo "Usage: ./update.sh /path/to/new-version" && exit 1
[ -f "data/flowjai.db" ] && cp data/flowjai.db data/flowjai.db.backup && echo "Database backed up."
cp -r "$1/backend/." backend/
cp -r "$1/frontend/dist/." frontend/dist/
[ -d "$1/wheels" ] && cp -r "$1/wheels/." wheels/
source venv/bin/activate
pip install --quiet -r backend/requirements.txt
cd backend && python3 -m alembic upgrade head && cd ..
echo "Update complete. Run ./launch.sh to start."
