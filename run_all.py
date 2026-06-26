"""Inicializador que lança dashboard + bandeja simultaneamente."""

import os
import sys
import time
import subprocess
import threading
import signal
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent


def run_dashboard():
    """Executa o dashboard em processo separado."""
    print("[Dashboard] Iniciando na porta 8888...")
    try:
        subprocess.run(
            [sys.executable, "pi_monitor_dashboard.py"],
            cwd=SCRIPT_DIR,
            check=False,
        )
    except KeyboardInterrupt:
        pass
    except Exception as e:
        print(f"[Dashboard] Erro: {e}")


def run_tray():
    """Executa o semáforo na bandeja."""
    print("[Tray] Iniciando semáforo...")
    try:
        subprocess.run(
            [sys.executable, "monitoramento_claude.py"],
            cwd=SCRIPT_DIR,
            check=False,
        )
    except KeyboardInterrupt:
        pass
    except Exception as e:
        print(f"[Tray] Erro: {e}")


def main():
    """Lança ambos os componentes."""
    print("╔════════════════════════════════════════════════════════╗")
    print("║   Pi Agent + Claude Code Monitor (Completo) 🚀         ║")
    print("╚════════════════════════════════════════════════════════╝")
    print("")
    print("Iniciando componentes...")
    print("")
    
    # Thread para dashboard
    dashboard_thread = threading.Thread(target=run_dashboard, daemon=False)
    dashboard_thread.start()
    
    # Aguarda um pouco para o dashboard iniciare
    time.sleep(2)
    
    # Thread para bandeja
    tray_thread = threading.Thread(target=run_tray, daemon=False)
    tray_thread.start()
    
    print("")
    print("═" * 56)
    print("  📊 Dashboard: http://localhost:8888")
    print("  📍 Bandeja: Verificar icone no topo da tela")
    print("═" * 56)
    print("")
    print("Pressione Ctrl+C para parar tudo")
    print("")
    
    try:
        # Aguarda as threads
        dashboard_thread.join()
        tray_thread.join()
    except KeyboardInterrupt:
        print("\n\n⏹️  Encerrando...")
        os._exit(0)


if __name__ == "__main__":
    main()
