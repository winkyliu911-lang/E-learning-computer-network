#!/bin/bash
set -e
cd "$(dirname "$0")"

echo "=== Rebuilding venv ==="
/usr/bin/python3 -m venv venv
echo "=== Installing dependencies ==="
./venv/bin/pip install --upgrade pip
./venv/bin/pip install -r requirements.txt
echo "=== Starting backend ==="
./venv/bin/python3 app.py
