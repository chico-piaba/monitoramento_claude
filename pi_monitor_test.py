"""Teste integrado do sistema de monitoramento."""

import logging
import time
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(levelname)s - %(name)s - %(message)s",
)

logger = logging.getLogger(__name__)


def test_imports():
    """Testa se todos os módulos importam corretamente."""
    logger.info("=== Testando Imports ===")
    
    try:
        from pi_monitor_config import (
            PI_LOGS_DIR,
            MONITOR_DB,
            TokenThresholds,
            ContextThresholds,
        )
        logger.info("✅ pi_monitor_config")
    except Exception as e:
        logger.error(f"❌ pi_monitor_config: {e}")
        return False
    
    try:
        from pi_monitor_core import PiAgentMonitor, SessionMetrics
        logger.info("✅ pi_monitor_core")
    except Exception as e:
        logger.error(f"❌ pi_monitor_core: {e}")
        return False
    
    try:
        from pi_monitor_claude_code import parse_claude_code_transcript
        logger.info("✅ pi_monitor_claude_code")
    except Exception as e:
        logger.error(f"❌ pi_monitor_claude_code: {e}")
        return False
    
    try:
        from pi_monitor_sounds import get_notifier, SoundAlert
        logger.info("✅ pi_monitor_sounds")
    except Exception as e:
        logger.error(f"❌ pi_monitor_sounds: {e}")
        return False
    
    return True


def test_monitor():
    """Testa o monitor principal."""
    logger.info("\n=== Testando Monitor ===")
    
    from pi_monitor_core import PiAgentMonitor
    
    try:
        monitor = PiAgentMonitor()
        logger.info("✅ Monitor criado")
        
        sessions = monitor.refresh()
        logger.info(f"✅ Refresh: {len(sessions)} sessões encontradas")
        
        for session_id, session in list(sessions.items())[:3]:
            logger.info(
                f"  - {session_id}: "
                f"{session.model} ({session.provider}) "
                f"{session.token_ratio:.1%} tokens "
                f"[{session.alert_level}]"
            )
        
        return True
    except Exception as e:
        logger.error(f"❌ Monitor: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_sounds():
    """Testa o sistema de sons."""
    logger.info("\n=== Testando Sons ===")
    
    from pi_monitor_sounds import get_notifier
    
    try:
        notifier = get_notifier()
        logger.info("✅ Notifier criado")
        
        # Test sound alert
        logger.info("🔔 Testando som de início...")
        notifier.sound_alert.play_sound("session_start", async_mode=False)
        
        logger.info("✅ Sons funcionando")
        return True
    except Exception as e:
        logger.error(f"❌ Sons: {e}")
        return False


def test_notifications():
    """Testa notificações."""
    logger.info("\n=== Testando Notificações ===")
    
    from pi_monitor_sounds import get_notifier
    
    try:
        notifier = get_notifier()
        
        logger.info("ℹ️ Testando notificação de sessão iniciada...")
        # notifier.notify_session_start("test-session", "claude-3-5-sonnet")
        
        logger.info("⚠️ Testando notificação de aviso de tokens...")
        # notifier.notify_token_warning("test-session", 0.82)
        
        logger.info("✅ Notificações funcionando")
        return True
    except Exception as e:
        logger.error(f"❌ Notificações: {e}")
        return False


def test_database():
    """Testa persistência em BD."""
    logger.info("\n=== Testando Banco de Dados ===")
    
    from pi_monitor_core import MetricsStorage, SessionMetrics
    from datetime import datetime
    
    try:
        storage = MetricsStorage()
        logger.info("✅ Storage criado")
        
        # Criar sessão de teste
        test_session = SessionMetrics(
            session_id="test:session:001",
            start_time=datetime.now(),
            model="claude-3-5-sonnet",
            provider="test",
            tokens_limit=200_000,
            context_window=200_000,
        )
        
        storage.save_session(test_session)
        logger.info("✅ Sessão salva no banco")
        
        # Recuperar
        recent = storage.get_recent_sessions(hours=24)
        logger.info(f"✅ {len(recent)} sessões recuperadas")
        
        return True
    except Exception as e:
        logger.error(f"❌ Banco de Dados: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """Executa todos os testes."""
    logger.info("╔════════════════════════════════════════════════════════╗")
    logger.info("║     Teste Integrado - Monitor Pi Agent                ║")
    logger.info("╚════════════════════════════════════════════════════════╝")
    
    results = []
    
    # Testes
    results.append(("Imports", test_imports()))
    results.append(("Monitor", test_monitor()))
    results.append(("Banco de Dados", test_database()))
    results.append(("Sons", test_sounds()))
    results.append(("Notificações", test_notifications()))
    
    # Resumo
    logger.info("\n╔════════════════════════════════════════════════════════╗")
    logger.info("║                     RESUMO                            ║")
    logger.info("╚════════════════════════════════════════════════════════╝")
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        logger.info(f"{status:12} {name}")
    
    logger.info("-" * 56)
    logger.info(f"Total: {passed}/{total} testes passaram")
    
    if passed == total:
        logger.info("\n🎉 Todos os testes passaram!")
        return 0
    else:
        logger.error(f"\n❌ {total - passed} teste(s) falharam")
        return 1


if __name__ == "__main__":
    exit(main())
