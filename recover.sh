#!/bin/bash
# YouClaw Emergency Recovery Script

echo "🛑 Phase 1: Terminating all existing neural threads..."
sudo fuser -k 8080/tcp 2>/dev/null
sudo pkill -9 -f youclaw || true
sudo pkill -9 -f python3 || true

echo "🧹 Phase 2: Clearing temporary cache..."
# No specific cache for now, but good for future

echo "📡 Phase 3: Synchronizing with GitHub (V5.4.4)..."
git pull

echo "🚀 Phase 4: Launching YouClaw V5.4.4..."
PYTHONPATH=src nohup .venv/bin/python3 -m youclaw.bot > youclaw.log 2>&1 &

echo "✅ Recovery Complete. Check your logs with: tail -f youclaw.log"
