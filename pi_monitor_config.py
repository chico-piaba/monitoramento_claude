"""Configurações centralizadas para monitoramento do pi agent."""

import os
from pathlib import Path
from dataclasses import dataclass
from typing import Dict, Optional

# ============================================================================
# CAMINHOS
# ============================================================================
PI_HOME = Path.home() / ".pi"
PI_LOGS_DIR = PI_HOME / "logs"
PI_SESSIONS_DIR = PI_HOME / "sessions"
PI_SETTINGS_FILE = PI_HOME / "settings.json"

MONITOR_HOME = Path.home() / ".pi_monitor"
MONITOR_DB = MONITOR_HOME / "metrics.db"
MONITOR_LOGS = MONITOR_HOME / "logs"
MONITOR_SOUNDS_DIR = MONITOR_HOME / "sounds"

# Criar diretórios se não existirem
MONITOR_HOME.mkdir(parents=True, exist_ok=True)
MONITOR_LOGS.mkdir(parents=True, exist_ok=True)
MONITOR_SOUNDS_DIR.mkdir(parents=True, exist_ok=True)

# ============================================================================
# ALERTAS E LIMITES
# ============================================================================
@dataclass
class TokenThresholds:
    """Limiares para avisos de tokens."""
    warning: float = 0.80      # 80% do limite -> aviso amarelo
    critical: float = 0.90     # 90% do limite -> aviso vermelho
    hard_limit: float = 0.99   # 99% -> bloqueio iminente

@dataclass
class ContextThresholds:
    """Limiares para avisos de contexto."""
    warning: float = 0.75      # 75% da janela -> aviso
    critical: float = 0.90     # 90% da janela -> crítico

# ============================================================================
# SONS E NOTIFICAÇÕES
# ============================================================================
SOUND_EVENTS = {
    "session_start": {
        "file": "bell_start.mp3",
        "volume": 0.5,
        "priority": "low",
    },
    "token_warning": {
        "file": "alert_warning.mp3",
        "volume": 0.7,
        "priority": "medium",
    },
    "context_critical": {
        "file": "alert_critical.mp3",
        "volume": 0.8,
        "priority": "high",
    },
    "error": {
        "file": "alert_error.mp3",
        "volume": 0.9,
        "priority": "critical",
    },
    "limit_reached": {
        "file": "alert_limit.mp3",
        "volume": 0.95,
        "priority": "critical",
    },
}

# ============================================================================
# CORES E ESTILOS
# ============================================================================
STATUS_COLORS = {
    "running": "#10b981",      # Verde
    "idle": "#f59e0b",         # Amarelo/Âmbar
    "error": "#ef4444",        # Vermelho
    "warning": "#fbbf24",      # Amarelo mais claro
    "critical": "#dc2626",     # Vermelho mais escuro
}

STATUS_EMOJI = {
    "running": "🟢",
    "idle": "🟡",
    "error": "🔴",
    "warning": "⚠️",
    "critical": "🚨",
    "info": "ℹ️",
}

# ============================================================================
# MODELO DE DADOS
# ============================================================================
MODEL_TOKEN_LIMITS = {
    "claude-3-5-sonnet": 200_000,
    "claude-3-opus": 200_000,
    "claude-3-haiku": 200_000,
    "gpt-4": 128_000,
    "gpt-4-turbo": 128_000,
    "gpt-3.5-turbo": 16_000,
}

MODEL_CONTEXT_WINDOWS = {
    "claude-3-5-sonnet": 200_000,
    "claude-3-opus": 200_000,
    "claude-3-haiku": 200_000,
    "gpt-4": 8_192,
    "gpt-4-turbo": 128_000,
    "gpt-3.5-turbo": 4_096,
}

# ============================================================================
# LOGGING
# ============================================================================
LOG_LEVEL = "INFO"
LOG_FORMAT = "[%(asctime)s] %(levelname)s - %(name)s - %(message)s"
LOG_FILE = MONITOR_LOGS / "monitor.log"

# ============================================================================
# INTERFACE WEB
# ============================================================================
WEB_HOST = "localhost"
WEB_PORT = 8888
WEB_REFRESH_INTERVAL = 2  # segundos entre atualizações WebSocket

# ============================================================================
# DETECÇÃO DE SUBAGENTS
# ============================================================================
SUBAGENT_PATTERNS = {
    "colony": r"(colony_pilot|ant_colony|colony)",
    "swarm": r"(swarm|task_swarm)",
    "nested": r"(nested_call|recursive_agent)",
    "cascade": r"(cascade|task_cascade)",
}

# ============================================================================
# HISTÓRICO
# ============================================================================
HISTORY_RETENTION_HOURS = 24  # manter histórico de 24 horas
MAX_EVENTS_PER_SESSION = 1000  # máximo de eventos por sessão em memória

# ============================================================================
# PROVIDER MAPPING (para interface amigável)
# ============================================================================
PROVIDER_NAMES = {
    "anthropic": "Claude (Anthropic)",
    "openai": "OpenAI",
    "groq": "Groq",
    "cohere": "Cohere",
    "together": "Together AI",
    "local": "Local Model",
}

# ============================================================================
# Função helper para obter limites por modelo
# ============================================================================
def get_token_limit(model: str) -> int:
    """Retorna o limite de tokens para um modelo."""
    for key, limit in MODEL_TOKEN_LIMITS.items():
        if key in model.lower():
            return limit
    return 100_000  # padrão conservador

def get_context_window(model: str) -> int:
    """Retorna a janela de contexto para um modelo."""
    for key, window in MODEL_CONTEXT_WINDOWS.items():
        if key in model.lower():
            return window
    return 32_000  # padrão conservador
