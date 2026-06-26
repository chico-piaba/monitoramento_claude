#!/bin/bash

echo "╔════════════════════════════════════════════════════╗"
echo "║   Iniciando Monitor Pi Agent + Claude Code         ║"
echo "╚════════════════════════════════════════════════════╝"
echo ""

# Terminal 1: Dashboard
echo "📊 Iniciando Dashboard (http://localhost:8888)..."
python3 pi_monitor_dashboard.py &
DASHBOARD_PID=$!
echo "   PID: $DASHBOARD_PID"
sleep 3

# Terminal 2: Bandeja
echo "📍 Iniciando Semáforo na Bandeja..."
python3 monitoramento_claude.py &
TRAY_PID=$!
echo "   PID: $TRAY_PID"

echo ""
echo "═══════════════════════════════════════════════════════"
echo "✅ Tudo iniciado!"
echo ""
echo "📊 Dashboard:  http://localhost:8888"
echo "📍 Bandeja:    Verificar ícone no topo da tela"
echo ""
echo "PIDs: Dashboard=$DASHBOARD_PID, Bandeja=$TRAY_PID"
echo ""
echo "Pressione Ctrl+C para parar"
echo "═══════════════════════════════════════════════════════"

wait
