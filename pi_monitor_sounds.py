"""Sistema de áudio com notificações e alertas."""

import logging
import tempfile
from pathlib import Path
from typing import Dict, Optional
from enum import Enum
from threading import Thread
import subprocess

from pi_monitor_config import (
    MONITOR_SOUNDS_DIR,
    SOUND_EVENTS,
    STATUS_EMOJI,
)

logger = logging.getLogger(__name__)


class AlertPriority(Enum):
    """Prioridades de alerta."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class SoundAlert:
    """Gerador de alertas sonoros."""
    
    def __init__(self, sounds_dir: Path = MONITOR_SOUNDS_DIR):
        self.sounds_dir = sounds_dir
        self.muted = False
        self.volume = 1.0  # 0.0 - 1.0
        self._mute_categories = set()  # Categorias de som mutadas
        self._thread_active = False
    
    def play_sound(self, event_type: str, volume: Optional[float] = None, async_mode: bool = True):
        """Reproduz um som de alerta.
        
        Args:
            event_type: Tipo de evento (ex: "token_warning", "error")
            volume: Volume 0-1 (sobrescreve o padrão)
            async_mode: Se True, reproduz em thread separada
        """
        if self.muted or event_type in self._mute_categories:
            logger.debug(f"Som {event_type} mutado")
            return
        
        event_config = SOUND_EVENTS.get(event_type)
        if not event_config:
            logger.warning(f"Tipo de evento desconhecido: {event_type}")
            return
        
        priority = event_config.get("priority", "low")
        sound_file = event_config.get("file")
        default_volume = event_config.get("volume", 1.0)
        
        # Use custom volume se fornecido
        final_volume = (volume if volume is not None else default_volume) * self.volume
        
        if async_mode:
            thread = Thread(
                target=self._play_sound_sync,
                args=(sound_file, final_volume, event_type),
                daemon=True,
            )
            thread.start()
        else:
            self._play_sound_sync(sound_file, final_volume, event_type)
    
    def _play_sound_sync(self, sound_file: str, volume: float, event_type: str):
        """Reproduz som de forma síncrona."""
        try:
            # Primeiro tenta usar afplay (macOS)
            if self._has_afplay():
                self._play_with_afplay(sound_file, volume)
            # Depois tenta usar paplay (Linux)
            elif self._has_paplay():
                self._play_with_paplay(sound_file, volume)
            # Se nenhum disponível, gera tom sintético
            else:
                self._play_synthetic_tone(event_type)
        except Exception as e:
            logger.error(f"Erro ao reproduzir som {event_type}: {e}")
    
    def _has_afplay(self) -> bool:
        """Verifica se afplay está disponível (macOS)."""
        result = subprocess.run(["which", "afplay"], capture_output=True)
        return result.returncode == 0
    
    def _has_paplay(self) -> bool:
        """Verifica se paplay está disponível (Linux)."""
        result = subprocess.run(["which", "paplay"], capture_output=True)
        return result.returncode == 0
    
    def _play_with_afplay(self, sound_file: str, volume: float):
        """Reproduz usando afplay (macOS)."""
        # Se o arquivo existe no diretório de sons, usa; caso contrário, gera tom
        sound_path = self.sounds_dir / sound_file
        
        if sound_path.exists():
            # afplay não suporta volume via CLI, então usa osascript
            subprocess.run(
                [
                    "osascript",
                    "-e",
                    f'set volume output volume {int(volume * 100)}',
                ],
                capture_output=True,
            )
            subprocess.run(
                ["afplay", str(sound_path)],
                capture_output=True,
            )
        else:
            self._play_synthetic_tone_afplay(sound_file)
    
    def _play_with_paplay(self, sound_file: str, volume: float):
        """Reproduz usando paplay (Linux)."""
        sound_path = self.sounds_dir / sound_file
        
        if sound_path.exists():
            subprocess.run(
                ["paplay", str(sound_path)],
                capture_output=True,
            )
    
    def _play_synthetic_tone(self, event_type: str):
        """Gera e reproduz tom sintético via terminal beep."""
        # Tons diferentes para diferentes tipos
        beep_count = {
            "error": 3,
            "context_critical": 2,
            "token_warning": 1,
            "session_start": 1,
            "limit_reached": 4,
        }.get(event_type, 1)
        
        for _ in range(beep_count):
            print("\a", end="", flush=True)
    
    def _play_synthetic_tone_afplay(self, event_type: str):
        """Gera tom via sintésis de voz no macOS."""
        messages = {
            "error": "Error",
            "context_critical": "Critical",
            "token_warning": "Warning",
            "session_start": "Started",
            "limit_reached": "Limit reached",
        }
        
        msg = messages.get(event_type, "Alert")
        subprocess.run(
            ["say", msg],
            capture_output=True,
        )
    
    def set_muted(self, muted: bool):
        """Muta/desmuta todos os sons."""
        self.muted = muted
        logger.info(f"Sons {'mutados' if muted else 'ativados'}")
    
    def set_volume(self, volume: float):
        """Define o volume geral (0.0-1.0)."""
        self.volume = max(0.0, min(1.0, volume))
        logger.info(f"Volume ajustado para {self.volume:.0%}")
    
    def toggle_mute_category(self, category: str):
        """Alterna mute para uma categoria específica."""
        if category in self._mute_categories:
            self._mute_categories.remove(category)
            logger.info(f"Categoria '{category}' desnutada")
        else:
            self._mute_categories.add(category)
            logger.info(f"Categoria '{category}' nutada")
    
    def is_muted(self) -> bool:
        """Retorna se os sons estão mudos."""
        return self.muted


class NotificationManager:
    """Gerencia notificações do sistema."""
    
    def __init__(self):
        self.sound_alert = SoundAlert()
    
    def notify_token_warning(self, session_id: str, ratio: float):
        """Notifica sobre aviso de tokens."""
        logger.warning(f"Token warning para {session_id}: {ratio:.1%}")
        self.sound_alert.play_sound("token_warning")
        self._send_notification(
            f"{STATUS_EMOJI.get('warning', '⚠️')} Aviso de Tokens",
            f"Sessão {session_id} usou {ratio:.1%} de tokens",
            priority="medium",
        )
    
    def notify_context_critical(self, session_id: str, ratio: float):
        """Notifica sobre contexto crítico."""
        logger.error(f"Context critical para {session_id}: {ratio:.1%}")
        self.sound_alert.play_sound("context_critical")
        self._send_notification(
            f"{STATUS_EMOJI.get('critical', '🚨')} Contexto Crítico",
            f"Sessão {session_id} usou {ratio:.1%} de contexto",
            priority="high",
        )
    
    def notify_error(self, session_id: str, error_msg: str):
        """Notifica sobre erro."""
        logger.error(f"Erro em {session_id}: {error_msg}")
        self.sound_alert.play_sound("error")
        self._send_notification(
            f"{STATUS_EMOJI.get('error', '🔴')} Erro",
            f"Sessão {session_id}: {error_msg}",
            priority="critical",
        )
    
    def notify_session_start(self, session_id: str, model: str):
        """Notifica sobre nova sessão."""
        logger.info(f"Sessão iniciada: {session_id} ({model})")
        self.sound_alert.play_sound("session_start")
        self._send_notification(
            f"{STATUS_EMOJI.get('info', 'ℹ️')} Sessão Iniciada",
            f"{session_id} com {model}",
            priority="low",
        )
    
    def notify_limit_reached(self, session_id: str):
        """Notifica sobre limite atingido."""
        logger.critical(f"Limite atingido para {session_id}")
        self.sound_alert.play_sound("limit_reached")
        self._send_notification(
            f"{STATUS_EMOJI.get('critical', '🚨')} Limite Atingido",
            f"Sessão {session_id} atingiu o limite de tokens",
            priority="critical",
        )
    
    def _send_notification(self, title: str, message: str, priority: str = "low"):
        """Envia notificação do sistema."""
        try:
            # macOS
            subprocess.run(
                [
                    "osascript",
                    "-e",
                    f'display notification "{message}" with title "{title}"',
                ],
                capture_output=True,
                timeout=2,
            )
        except Exception as e:
            logger.debug(f"Falha ao enviar notificação: {e}")


# Instância global
_global_notifier: Optional[NotificationManager] = None


def get_notifier() -> NotificationManager:
    """Retorna a instância global do NotificationManager."""
    global _global_notifier
    if _global_notifier is None:
        _global_notifier = NotificationManager()
    return _global_notifier
