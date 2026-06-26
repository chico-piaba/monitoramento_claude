#!/bin/bash
# Quick Start - Monitor Pi Agent + Claude Code

set -e

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$SCRIPT_DIR"

echo "╔════════════════════════════════════════════════════════╗"
echo "║        Pi Agent + Claude Code Monitor Setup           ║"
echo "╚════════════════════════════════════════════════════════╝"
echo ""

# 1. Check Python
echo "1️⃣  Verificando Python..."
python3 --version || { echo "❌ Python 3 não encontrado"; exit 1; }
echo "✅ Python OK"
echo ""

# 2. Install dependencies
echo "2️⃣  Instalando dependências..."
pip install -r requirements.txt --quiet
echo "✅ Dependências instaladas"
echo ""

# 3. Run tests
echo "3️⃣  Executando testes..."
python3 pi_monitor_test.py
TESTS_RESULT=$?
echo ""

if [ $TESTS_RESULT -ne 0 ]; then
    echo "⚠️  Alguns testes falharam, mas continuando..."
    echo ""
fi

# 4. Show usage
echo "╔════════════════════════════════════════════════════════╗"
echo "║                    PRONTO! 🚀                          ║"
echo "╚════════════════════════════════════════════════════════╝"
echo ""
echo "Opções de inicialização:"
echo ""
echo "  📊 Dashboard Web:"
echo "     python3 pi_monitor_dashboard.py"
echo "     Acesse: http://localhost:8888"
echo ""
echo "  📍 Semáforo na Bandeja:"
echo "     python3 monitoramento_claude.py"
echo ""
echo "  🧪 Teste Integrado:"
echo "     python3 pi_monitor_test.py"
echo ""
echo "  📚 Documentação:"
echo "     cat README_NEW.md"
echo ""
echo "╚════════════════════════════════════════════════════════╝"
