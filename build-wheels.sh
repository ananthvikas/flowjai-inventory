#!/bin/bash
cd "$(dirname "$0")"
mkdir -p wheels
echo "Downloading packages for offline distribution..."
pip download --dest wheels -r backend/requirements.txt
echo "Done. Include wheels/ in your distribution package."
