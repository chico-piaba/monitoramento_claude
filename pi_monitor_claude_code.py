"""Extensões de parsing para Claude Code transcripts."""

import json
import logging
from pathlib import Path
from datetime import datetime
from typing import List, Optional

from pi_monitor_core import SessionMetrics

logger = logging.getLogger(__name__)


def parse_claude_code_transcript(jsonl_file: Path, project_name: str) -> Optional[SessionMetrics]:
    """Parse de um transcript do Claude Code (~/.claude/projects/*/[session].jsonl).
    
    Extrai:
    - Título da sessão (aiTitle)
    - Tokens totais usados (input + output)
    - Status (running, idle, error)
    - Timestamp da última mensagem
    """
    if not jsonl_file.exists():
        return None
    
    # Session ID baseado no projeto e arquivo
    session_id = f"claude-code:{project_name}:{jsonl_file.stem}"
    mtime = jsonl_file.stat().st_mtime
    
    session = SessionMetrics(
        session_id=session_id,
        start_time=datetime.fromtimestamp(mtime),
        model="claude-3-5-sonnet",  # Claude Code usa sempre Sonnet
        provider="claude_code",
        status="running",
        tokens_limit=200_000,
        context_window=200_000,
    )
    
    # Lê apenas o fim do arquivo (transcripts podem ser grandes)
    lines = _read_file_tail(jsonl_file, nbytes=131072)  # 128KB
    
    total_input_tokens = 0
    total_output_tokens = 0
    last_turn_assistant = False
    session_title = None
    
    for line in lines:
        try:
            data = json.loads(line)
            msg_type = data.get("type")
            
            # Extrai título da sessão
            if msg_type == "ai-title" and "aiTitle" in data:
                session_title = data["aiTitle"]
            
            # Conta tokens de messages
            if msg_type in ("assistant", "user"):
                message = data.get("message") or {}
                
                # Tenta extrair token counts
                if "tokens" in message:
                    if "input" in message["tokens"]:
                        total_input_tokens += message["tokens"]["input"]
                    if "output" in message["tokens"]:
                        total_output_tokens += message["tokens"]["output"]
                
                role = message.get("role")
                if role == "assistant":
                    last_turn_assistant = True
                elif role == "user":
                    last_turn_assistant = False
            
            # Detecta erro
            content = data.get("message", {}).get("content", [])
            if isinstance(content, list):
                for item in content:
                    if isinstance(item, dict) and item.get("type") == "tool_result" and item.get("is_error"):
                        session.status = "error"
                        session.error_message = item.get("content", "Erro desconhecido")
        
        except json.JSONDecodeError:
            continue
        except Exception as e:
            logger.debug(f"Erro ao parsear linha Claude Code: {e}")
    
    session.tokens_used = total_input_tokens + total_output_tokens
    session.context_used = total_input_tokens
    
    # Se último turno foi do assistant, está produzindo; caso contrário, idle
    if session.status != "error":
        session.status = "running" if last_turn_assistant else "idle"
    
    return session


def _read_file_tail(path: Path, nbytes: int = 131072) -> List[str]:
    """Lê apenas o fim do arquivo (para performance com arquivos grandes)."""
    try:
        with open(path, "rb") as f:
            f.seek(0, 2)  # Fim do arquivo
            tamanho = f.tell()
            f.seek(max(0, tamanho - nbytes))
            dados = f.read()
        
        linhas = dados.decode("utf-8", "ignore").splitlines()
        if tamanho > nbytes and linhas:
            linhas = linhas[1:]  # descarta a primeira linha (possivelmente parcial)
        return linhas
    except Exception as e:
        logger.error(f"Erro ao ler cauda do arquivo {path}: {e}")
        return []
