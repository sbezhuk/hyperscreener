#!/bin/bash

# Hyperscreener launch script
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "🚀 Запуск Hyperliquid Screener & Terminal..."

# 1. Start Backend
echo "🔹 Запуск FastAPI бекенду (port 8000)..."
cd "$ROOT_DIR/backend"
source .venv/bin/activate
python3 run.py > /dev/null 2>&1 &
BACKEND_PID=$!

# 2. Start Frontend
echo "🔹 Запуск Vite фронтенду (port 3000)..."
cd "$ROOT_DIR/frontend"
npm run dev -- --port 3000 > /dev/null 2>&1 &
FRONTEND_PID=$!

echo ""
echo "✅ Термінал успішно запущено!"
echo "👉 Відкрийте у браузері: http://localhost:3000"
echo "👉 Бекенд API: http://localhost:8000/docs"
echo ""
echo "Для зупинки натисніть Ctrl+C"

trap "kill $BACKEND_PID $FRONTEND_PID; exit 0" SIGINT SIGTERM
wait
