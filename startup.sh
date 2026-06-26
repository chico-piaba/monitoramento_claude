#!/bin/bash
set -e

cd "$(dirname "$0")"

echo "╔════════════════════════════════════════════════════╗"
echo "║  Iniciando Monitor Pi Agent + Claude Code          ║"
echo "╚════════════════════════════════════════════════════╝"
echo ""

# Terminal 1: Dashboard
echo "📊 Iniciando Dashboard (http://localhost:9000)..."
nohup python3 -u << 'DASHBOARD' > dashboard.log 2>&1 &
import sys
sys.path.insert(0, '.')
from pi_monitor_dashboard import app
import uvicorn

uvicorn.run(app, host="127.0.0.1", port=9000, log_level="info")
DASHBOARD

DASHBOARD_PID=$!
echo "   Dashboard PID: $DASHBOARD_PID"
sleep 3

# Terminal 2: Bandeja
echo "📍 Iniciando Semáforo na Bandeja..."
nohup python3 -u monitoramento_claude.py > tray.log 2>&1 &
TRAY_PID=$!
echo "   Bandeja PID: $TRAY_PID"
sleep 2

echo ""
echo "═════════════════════════════════════════════════════"
echo "✅ Tudo iniciado!"
echo ""
echo "📊 Dashboard:  http://localhost:9000"
echo "📍 Bandeja:    Verificar ícone no topo"
echo ""
echo "PIDs:"
echo "   Dashboard: $DASHBOARD_PID"
echo "   Bandeja:   $TRAY_PID"
echo ""
echo "Logs:"
echo "   tail -f dashboard.log"
echo "   tail -f tray.log"
echo ""
echo "═════════════════════════════════════════════════════"

wait
