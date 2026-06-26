"""Dashboard Web do Monitor Pi Agent + Claude Code."""

import json
import logging
import os
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional
from urllib import request as urlrequest
from urllib.error import URLError

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
import asyncio
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from pi_monitor_sounds import get_notifier
import monitoramento_claude as tray_monitor

logger = logging.getLogger(__name__)

# ============================================================================
# MODELOS DE RESPOSTA
# ============================================================================
CONTEXT_DEFAULT = 200_000
SNAP_DB = Path.home() / ".pi_monitor" / "metrics.db"
LMSTUDIO_BASE = os.getenv("LMSTUDIO_BASE", "http://localhost:1234/v1")
LMSTUDIO_MODEL = os.getenv("LMSTUDIO_MODEL", "gemma-4")
LMSTUDIO_API_KEY = os.getenv("LMSTUDIO_API_KEY", "")
LMSTUDIO_CHAT_URL = os.getenv("LMSTUDIO_CHAT_URL", "")  # override total, ex: http://localhost:1234/chat/completions
LM_CLASSIFIER_ENABLED = os.getenv("LM_CLASSIFIER_ENABLED", "1") == "1"
LM_CLASSIFIER_TIMEOUT_S = float(os.getenv("LM_CLASSIFIER_TIMEOUT_S", "3.0"))
LM_CLASSIFY_ONLY_ATTENTION = os.getenv("LM_CLASSIFY_ONLY_ATTENTION", "1") == "1"

# cache simples para não chamar classificador a cada refresh
_STAGE_CACHE: Dict[str, dict] = {}

# pricing aproximado por 1M tokens (input, output)
PRICE_TABLE = {
    "sonnet": (3.0, 15.0),
    "opus": (15.0, 75.0),
    "haiku": (0.25, 1.25),
    "gpt-4o": (5.0, 15.0),
    "gpt-4": (10.0, 30.0),
    "gpt-3.5": (0.5, 1.5),
    "gemini": (1.25, 5.0),
    # fallback para ecossistema Codex/Copilot (aprox. conservadora)
    "codex": (5.0, 15.0),
    "copilot": (5.0, 15.0),
}


class SessionView(BaseModel):
    """View simplificada de uma sessão ativa da tray."""
    session_id: str
    project_name: str
    source: str  # "pi" ou "claude"
    model: str
    provider: str
    status: str
    alert_level: str
    tokens_used: int
    tokens_limit: int
    token_ratio: float
    context_used: int
    context_window: int
    context_ratio: float
    duration_seconds: int
    error_message: Optional[str] = None
    has_subagents: bool = False
    context_excerpt: Optional[str] = None
    needs_attention: bool = False
    cost_usd: float = 0.0
    stage: str = "working"
    next_action: str = "—"
    lm_status: str = "heuristic"

    @staticmethod
    def from_tray_instance(inst: dict, now_ts: float, usage: dict) -> "SessionView":
        status = {
            "green": "running",
            "yellow": "idle",
            "red": "error",
        }.get(inst.get("cor"), "idle")
        alert_level = {
            "green": "info",
            "yellow": "warning",
            "red": "critical",
        }.get(inst.get("cor"), "info")
        # Mostra tempo no estado atual (mais útil que tempo desde último evento bruto).
        base_ts = inst.get("mudou_em") or inst.get("last_ts") or now_ts
        dur = int(max(0, now_ts - base_ts))
        excerpt = inst.get("last_prompt")
        if isinstance(excerpt, str):
            excerpt = excerpt.strip().replace("\n", " ")[:180]
        tokens_total = int(usage.get("tokens_total", 0))
        tokens_in = int(usage.get("tokens_in", 0))
        tokens_out = int(usage.get("tokens_out", 0))
        context_used = int(usage.get("context_used", tokens_in))
        context_window = int(usage.get("context_window", CONTEXT_DEFAULT))
        token_ratio = (tokens_total / context_window) if context_window else 0.0
        context_ratio = (context_used / context_window) if context_window else 0.0

        return SessionView(
            session_id=inst.get("sid", "unknown"),
            project_name=inst.get("projeto") or inst.get("titulo") or "Desconhecido",
            source=inst.get("fonte", "claude"),
            model=usage.get("model") or "—",
            provider=usage.get("provider") or inst.get("fonte", "claude"),
            status=status,
            alert_level=alert_level,
            tokens_used=tokens_total,
            tokens_limit=context_window,
            token_ratio=token_ratio,
            context_used=context_used,
            context_window=context_window,
            context_ratio=context_ratio,
            duration_seconds=dur,
            error_message=None,
            has_subagents=False,
            context_excerpt=excerpt,
            needs_attention=bool(inst.get("needs_attention")),
            cost_usd=float(usage.get("cost_usd", 0.0)),
            stage=usage.get("stage", "working"),
            next_action=usage.get("next_action", "—"),
            lm_status=usage.get("lm_status", "heuristic"),
        )


class DashboardState(BaseModel):
    """Estado completo do dashboard."""
    timestamp: str
    total_sessions: int
    total_tokens_used: int
    estimated_cost: float
    sessions: List[SessionView]
    alert_count: int
    pending_items: List[str]
    last_actions: List[str]


# ============================================================================
# APLICAÇÃO FASTAPI
# ============================================================================
app = FastAPI(
    title="Pi Agent + Claude Code Monitor",
    description="Dashboard de monitoramento em tempo real",
)

# Monitor singleton
notifier = get_notifier()

# WebSocket connections
active_connections: List[WebSocket] = []


def _price_usd_per_million(provider: str, model: str, source: str = ""):
    p = (provider or "").lower()
    m = (model or "").lower()
    for key, prices in PRICE_TABLE.items():
        if key in m:
            return prices
    if "anthropic" in p or source == "claude":
        return PRICE_TABLE["sonnet"]
    if "copilot" in p:
        return PRICE_TABLE["copilot"]
    if "openai" in p:
        return PRICE_TABLE["gpt-4"]
    return (0.0, 0.0)


def _heuristic_stage(status: str, needs_attention: bool, text: str):
    t = (text or "").lower()
    if status == "error" or "erro" in t or "failed" in t:
        return ("blocked", "Resolver erro e retomar execução")
    if needs_attention or "aguard" in t or "confirm" in t:
        return ("waiting_user", "Responder/confirmar próximo passo")
    if any(k in t for k in ["test", "pytest", "chec", "valid"]):
        return ("testing", "Revisar resultados dos testes")
    if any(k in t for k in ["plan", "planej", "arquitet", "estratég"]):
        return ("planning", "Definir e priorizar próximos passos")
    return ("executing", "Acompanhar execução automática")


def _classify_stage_lm(text: str, status: str, needs_attention: bool):
    if not LM_CLASSIFIER_ENABLED:
        return None

    payload = {
        "model": LMSTUDIO_MODEL,
        "temperature": 0.1,
        "messages": [
            {
                "role": "system",
                "content": (
                    "Classifique a etapa de trabalho em JSON estrito com chaves: "
                    "stage (planning|executing|testing|blocked|waiting_user|done), "
                    "next_action (string curta), confidence (0..1)."
                ),
            },
            {
                "role": "user",
                "content": f"status={status}; needs_attention={needs_attention}; contexto={text[:1000]}",
            },
        ],
    }

    headers = {"Content-Type": "application/json"}
    if LMSTUDIO_API_KEY:
        headers["Authorization"] = f"Bearer {LMSTUDIO_API_KEY}"

    base = LMSTUDIO_BASE.rstrip("/")
    candidates = []
    if LMSTUDIO_CHAT_URL:
        candidates.append(LMSTUDIO_CHAT_URL)
    candidates.extend([
        f"{base}/chat/completions",
        f"{base}/responses",
    ])
    # evita duplicatas mantendo ordem
    seen = set()
    endpoints = [u for u in candidates if not (u in seen or seen.add(u))]

    for endpoint in endpoints:
        try:
            req = urlrequest.Request(
                endpoint,
                data=json.dumps(payload).encode("utf-8"),
                headers=headers,
                method="POST",
            )
            with urlrequest.urlopen(req, timeout=LM_CLASSIFIER_TIMEOUT_S) as resp:
                data = json.loads(resp.read().decode("utf-8"))

            # OpenAI chat-completions
            content = None
            if isinstance(data, dict) and data.get("choices"):
                content = data["choices"][0].get("message", {}).get("content")
            # Responses API-style
            if not content and isinstance(data, dict):
                content = data.get("output_text")

            if not content:
                continue

            start = content.find("{")
            end = content.rfind("}")
            if start >= 0 and end > start:
                return json.loads(content[start:end + 1])
        except (URLError, TimeoutError, KeyError, ValueError, json.JSONDecodeError):
            continue

    return None


def _extract_usage_from_transcript(path: str, status: str = "running", needs_attention: bool = False, context_hint: str = "", source: str = "") -> dict:
    usage = {
        "tokens_in": 0,
        "tokens_out": 0,
        "tokens_total": 0,
        "context_used": 0,
        "context_window": CONTEXT_DEFAULT,
        "provider": None,
        "model": None,
        "cost_usd": 0.0,
        "stage": "working",
        "next_action": "—",
        "lm_status": "heuristic",
    }
    if not path or not os.path.isfile(path):
        return usage

    try:
        mtime = os.path.getmtime(path)

        cache_key = path
        cached = _STAGE_CACHE.get(cache_key)

        with open(path, "rb") as f:
            f.seek(0, os.SEEK_END)
            size = f.tell()
            f.seek(max(0, size - 196608))
            raw = f.read().decode("utf-8", "ignore").splitlines()
            if size > 196608 and raw:
                raw = raw[1:]
    except OSError:
        return usage

    last_text_chunks = []

    for ln in raw:
        try:
            o = json.loads(ln)
        except json.JSONDecodeError:
            continue

        msg = o.get("message") or {}
        usage_obj = msg.get("usage") or o.get("usage") or {}

        # Provider/model
        usage["provider"] = msg.get("provider") or o.get("provider") or usage["provider"]
        usage["model"] = msg.get("model") or o.get("modelId") or o.get("model") or usage["model"]

        # Campos comuns de token
        ti = (
            usage_obj.get("input_tokens")
            or usage_obj.get("prompt_tokens")
            or usage_obj.get("inputTokens")
            or 0
        )
        to = (
            usage_obj.get("output_tokens")
            or usage_obj.get("completion_tokens")
            or usage_obj.get("outputTokens")
            or 0
        )
        tt = usage_obj.get("total_tokens") or usage_obj.get("totalTokens") or 0

        if ti:
            usage["tokens_in"] += int(ti)
        if to:
            usage["tokens_out"] += int(to)
        if tt:
            usage["tokens_total"] = max(usage["tokens_total"], int(tt))

        # Captura texto para classificar etapa
        content = msg.get("content")
        if isinstance(content, list):
            for c in content:
                if isinstance(c, dict) and c.get("type") == "text" and c.get("text"):
                    last_text_chunks.append(str(c.get("text"))[:200])
        elif isinstance(content, str):
            last_text_chunks.append(content[:200])

    if usage["tokens_total"] == 0:
        usage["tokens_total"] = usage["tokens_in"] + usage["tokens_out"]

    usage["context_used"] = usage["tokens_in"]

    # fallback de modelo/provider por fonte
    if not usage["provider"]:
        usage["provider"] = source or "unknown"
    if not usage["model"] and source == "claude":
        usage["model"] = "claude-3-5-sonnet"

    in_price, out_price = _price_usd_per_million(usage["provider"], usage["model"], source=source)

    # quando só temos total_tokens (sem split), usa divisão 50/50 para estimativa
    tokens_in_cost = usage["tokens_in"]
    tokens_out_cost = usage["tokens_out"]
    if usage["tokens_total"] > 0 and tokens_in_cost == 0 and tokens_out_cost == 0:
        tokens_in_cost = usage["tokens_total"] // 2
        tokens_out_cost = usage["tokens_total"] - tokens_in_cost

    usage["cost_usd"] = (tokens_in_cost / 1_000_000) * in_price + (tokens_out_cost / 1_000_000) * out_price

    # Stage / next action: cache + LM classifier + fallback heurístico
    text_for_stage = " | ".join(last_text_chunks[-8:])
    if context_hint:
        text_for_stage = f"{context_hint} | {text_for_stage}"

    stage, next_action = _heuristic_stage(status, needs_attention, text_for_stage)

    if cached and cached.get("mtime") == mtime:
        usage["stage"] = cached.get("stage", stage)
        usage["next_action"] = cached.get("next_action", next_action)
        usage["lm_status"] = cached.get("lm_status", "cache")
    else:
        should_call_lm = LM_CLASSIFIER_ENABLED and (needs_attention or not LM_CLASSIFY_ONLY_ATTENTION)
        classified = _classify_stage_lm(text_for_stage, status=status, needs_attention=needs_attention) if should_call_lm else None
        if classified and classified.get("stage"):
            usage["stage"] = classified.get("stage")
            usage["next_action"] = classified.get("next_action") or next_action
            usage["lm_status"] = "lm_ok"
        else:
            usage["stage"] = stage
            usage["next_action"] = next_action
            usage["lm_status"] = "heuristic" if not should_call_lm else "lm_fallback"

        _STAGE_CACHE[cache_key] = {
            "mtime": mtime,
            "stage": usage["stage"],
            "next_action": usage["next_action"],
            "lm_status": usage["lm_status"],
        }

    return usage


def _persist_snapshot(state: "DashboardState"):
    SNAP_DB.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(SNAP_DB) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS dashboard_snapshots (
              ts TEXT PRIMARY KEY,
              total_sessions INTEGER,
              total_tokens INTEGER,
              total_cost REAL,
              payload_json TEXT
            )
            """
        )
        conn.execute(
            "INSERT OR REPLACE INTO dashboard_snapshots (ts,total_sessions,total_tokens,total_cost,payload_json) VALUES (?,?,?,?,?)",
            (
                state.timestamp,
                state.total_sessions,
                state.total_tokens_used,
                state.estimated_cost,
                state.json(),
            ),
        )
        conn.commit()


# ============================================================================
# ROTAS HTTP
# ============================================================================
@app.get("/", response_class=HTMLResponse)
async def dashboard():
    """Retorna o HTML do dashboard."""
    return HTML_TEMPLATE


@app.get("/api/state")
async def get_state() -> DashboardState:
    """Retorna o estado completo do dashboard usando a mesma lógica ativa da tray."""
    tray_monitor.monitor.coletar()
    instancias, _, _ = tray_monitor.monitor.snapshot()
    now_ts = datetime.now().timestamp()

    session_views: List[SessionView] = []
    total_tokens = 0
    total_cost = 0.0

    for inst in instancias:
        mapped_status = {
            "green": "running",
            "yellow": "idle",
            "red": "error",
        }.get(inst.get("cor"), "idle")
        usage = _extract_usage_from_transcript(
            inst.get("transcript_path"),
            status=mapped_status,
            needs_attention=bool(inst.get("needs_attention")),
            context_hint=inst.get("last_prompt") or "",
            source=inst.get("fonte", ""),
        )
        sv = SessionView.from_tray_instance(inst, now_ts, usage)
        session_views.append(sv)
        total_tokens += sv.tokens_used
        total_cost += sv.cost_usd

    alert_count = sum(1 for s in session_views if s.alert_level in ("warning", "critical"))

    pending_items = []
    for s in session_views:
        if s.needs_attention:
            pending_items.append(f"{s.project_name}: {s.next_action}")
        elif s.status == "error":
            pending_items.append(f"{s.project_name}: corrigir erro")
        elif s.alert_level == "warning":
            pending_items.append(f"{s.project_name}: aguardando ação")
    pending_items = pending_items[:8]

    last_actions = [
        f"{s.project_name}: {s.stage} · {s.status} ({s.duration_seconds}s)"
        for s in sorted(session_views, key=lambda x: x.duration_seconds)[:8]
    ]

    state = DashboardState(
        timestamp=datetime.now().isoformat(),
        total_sessions=len(session_views),
        total_tokens_used=total_tokens,
        estimated_cost=total_cost,
        sessions=session_views,
        alert_count=alert_count,
        pending_items=pending_items,
        last_actions=last_actions,
    )
    _persist_snapshot(state)
    return state


# ============================================================================
# WEBSOCKET
# ============================================================================
@app.get("/mobile", response_class=HTMLResponse)
async def mobile_dashboard():
    """Versão compacta para celular."""
    return MOBILE_HTML_TEMPLATE


@app.websocket("/ws/monitor")
async def websocket_monitor(websocket: WebSocket):
    """WebSocket para streaming de atualizações em tempo real."""
    await websocket.accept()
    active_connections.append(websocket)

    try:
        while True:
            state = await get_state()
            await websocket.send_json(state.dict())
            await asyncio.sleep(2)
    except WebSocketDisconnect:
        pass
    finally:
        if websocket in active_connections:
            active_connections.remove(websocket)


# ============================================================================
# HTML DO DASHBOARD
# ============================================================================
HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="pt-BR">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Pi Agent + Claude Code Monitor</title>
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }
        
        body {
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
            background: linear-gradient(135deg, #0f172a 0%, #1e293b 100%);
            color: #e2e8f0;
            min-height: 100vh;
            padding: 20px;
        }
        
        .container {
            max-width: 1600px;
            margin: 0 auto;
        }
        
        header {
            margin-bottom: 30px;
        }
        
        h1 {
            font-size: 2.5rem;
            margin-bottom: 10px;
            background: linear-gradient(135deg, #00d4ff, #0099ff);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            background-clip: text;
        }
        
        .stats {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 15px;
            margin-bottom: 30px;
        }
        
        .stat-card {
            background: rgba(30, 41, 59, 0.7);
            border: 1px solid rgba(148, 163, 184, 0.2);
            border-radius: 8px;
            padding: 20px;
            backdrop-filter: blur(10px);
        }
        
        .stat-label {
            font-size: 0.875rem;
            color: #94a3b8;
            text-transform: uppercase;
            letter-spacing: 0.05em;
            margin-bottom: 8px;
        }
        
        .stat-value {
            font-size: 1.875rem;
            font-weight: 700;
            color: #00d4ff;
        }
        
        .sessions-grid {
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(350px, 1fr));
            gap: 20px;
        }
        
        .session-card {
            background: rgba(30, 41, 59, 0.7);
            border: 1px solid rgba(148, 163, 184, 0.2);
            border-radius: 12px;
            padding: 20px;
            backdrop-filter: blur(10px);
            transition: all 0.3s ease;
            position: relative;
            overflow: hidden;
        }
        
        .session-card:hover {
            border-color: rgba(0, 212, 255, 0.5);
            box-shadow: 0 0 20px rgba(0, 212, 255, 0.1);
        }
        
        .session-card.alert-warning {
            border-color: #fbbf24;
            box-shadow: 0 0 15px rgba(251, 191, 36, 0.15);
        }
        
        .session-card.alert-critical {
            border-color: #ef4444;
            box-shadow: 0 0 15px rgba(239, 68, 68, 0.15);
        }
        
        .session-card::before {
            content: "";
            position: absolute;
            top: 0;
            left: 0;
            width: 100%;
            height: 3px;
            background: linear-gradient(90deg, #00d4ff, #0099ff);
        }
        
        .session-card.alert-warning::before {
            background: linear-gradient(90deg, #fbbf24, #f59e0b);
        }
        
        .session-card.alert-critical::before {
            background: linear-gradient(90deg, #ef4444, #dc2626);
        }
        
        .session-header {
            margin-bottom: 15px;
        }
        
        .session-title {
            font-size: 1.125rem;
            font-weight: 600;
            margin-bottom: 5px;
            display: flex;
            align-items: center;
            gap: 8px;
        }
        
        .session-badge {
            display: inline-block;
            padding: 4px 8px;
            border-radius: 4px;
            font-size: 0.75rem;
            font-weight: 600;
            text-transform: uppercase;
            background: rgba(148, 163, 184, 0.2);
        }
        
        .session-badge.pi {
            background: rgba(147, 51, 234, 0.2);
            color: #d8b4fe;
        }
        
        .session-badge.claude {
            background: rgba(59, 130, 246, 0.2);
            color: #bfdbfe;
        }
        
        .session-meta {
            font-size: 0.875rem;
            color: #94a3b8;
            margin-bottom: 12px;
        }
        
        .progress-bar {
            height: 8px;
            background: rgba(148, 163, 184, 0.2);
            border-radius: 4px;
            overflow: hidden;
            margin-bottom: 8px;
        }
        
        .progress-fill {
            height: 100%;
            background: linear-gradient(90deg, #00d4ff, #0099ff);
            border-radius: 4px;
            transition: width 0.3s ease;
        }
        
        .progress-label {
            display: flex;
            justify-content: space-between;
            font-size: 0.875rem;
            margin-bottom: 5px;
        }
        
        .loading {
            text-align: center;
            padding: 40px;
            color: #94a3b8;
        }
        
        .spinner {
            width: 40px;
            height: 40px;
            border: 3px solid rgba(148, 163, 184, 0.2);
            border-top: 3px solid #00d4ff;
            border-radius: 50%;
            animation: spin 1s linear infinite;
            margin: 0 auto 20px;
        }
        
        @keyframes spin {
            0% { transform: rotate(0deg); }
            100% { transform: rotate(360deg); }
        }
        
        .status-indicator {
            display: inline-block;
            width: 8px;
            height: 8px;
            border-radius: 50%;
            margin-right: 6px;
        }
        
        .status-running { background: #10b981; }
        .status-idle { background: #f59e0b; }
        .status-error { background: #ef4444; }
    </style>
</head>
<body>
    <div class="container">
        <header>
            <h1>🚀 Monitor Pi Agent + Claude Code</h1>
            <p style="color: #94a3b8;">Dashboard de Sessões e Tokens em Tempo Real</p>
        </header>
        
        <div class="stats" id="stats">
            <div class="stat-card">
                <div class="stat-label">Sessões Ativas</div>
                <div class="stat-value" id="stat-sessions">0</div>
            </div>
            <div class="stat-card">
                <div class="stat-label">Tokens Usados</div>
                <div class="stat-value" id="stat-tokens">0</div>
            </div>
            <div class="stat-card">
                <div class="stat-label">Custo Estimado</div>
                <div class="stat-value" id="stat-cost">$0.00</div>
            </div>
            <div class="stat-card">
                <div class="stat-label">Alertas</div>
                <div class="stat-value" id="stat-alerts">0</div>
            </div>
        </div>
        
        <div id="content">
            <div class="loading">
                <div class="spinner"></div>
                <p>Carregando dados...</p>
            </div>
        </div>
    </div>
    
    <script>
        const ws = new WebSocket(`ws://${window.location.host}/ws/monitor`);
        
        ws.onmessage = (event) => {
            const state = JSON.parse(event.data);
            updateDashboard(state);
        };
        
        ws.onerror = () => {
            // Fallback para polling se WebSocket falhar
            setInterval(fetchState, 2000);
            fetchState();
        };
        
        async function fetchState() {
            try {
                const response = await fetch('/api/state');
                const state = await response.json();
                updateDashboard(state);
            } catch (e) {
                console.error('Erro ao buscar estado:', e);
            }
        }
        
        function updateDashboard(state) {
            // Stats
            document.getElementById('stat-sessions').textContent = state.total_sessions;
            document.getElementById('stat-tokens').textContent = formatNumber(state.total_tokens_used);
            document.getElementById('stat-cost').textContent = `$${state.estimated_cost.toFixed(2)}`;
            document.getElementById('stat-alerts').textContent = state.alert_count;
            
            // Sessions grid + pendências
            const content = document.getElementById('content');
            const pendingHtml = `
                <div class="stat-card" style="margin-bottom:16px;">
                    <div class="stat-label">Pendências / Próximas ações</div>
                    <div style="font-size:0.95rem; line-height:1.5; color:#cbd5e1;">
                        ${(state.pending_items && state.pending_items.length)
                            ? state.pending_items.map(i => `• ${i}`).join('<br>')
                            : '• Sem pendências críticas agora'}
                    </div>
                </div>`;
            content.innerHTML = pendingHtml + `<div class="sessions-grid">${
                state.sessions.map(renderSession).join('')
            }</div>`;
            
            if (state.sessions.length === 0) {
                content.innerHTML = pendingHtml + '<div class="loading"><p>Nenhuma sessão ativa</p></div>';
            }
        }
        
        function renderSession(session) {
            const statusClass = `status-${session.status}`;
            const alertClass = session.alert_level !== 'info' ? `alert-${session.alert_level}` : '';
            const source = (session.source === 'claude_code' || session.source === 'claude') ? 'claude' : 'pi';
            
            return `
                <div class="session-card ${alertClass}">
                    <div class="session-header">
                        <div class="session-title">
                            <span class="status-indicator ${statusClass}"></span>
                            ${session.project_name}
                            <span class="session-badge ${source}">${source}</span>
                        </div>
                        <div class="session-meta">
                            ${session.model} • ${formatTime(session.duration_seconds)} • etapa: ${session.stage}
                            ${session.needs_attention ? ' • ⚠️ aguardando você' : ''}
                        </div>
                    </div>
                    
                    <div>
                        <div class="progress-label">
                            <span>Tokens</span>
                            <span>${formatNumber(session.tokens_used)}/${formatNumber(session.tokens_limit)}</span>
                        </div>
                        <div class="progress-bar">
                            <div class="progress-fill" style="width: ${(session.token_ratio * 100).toFixed(1)}%"></div>
                        </div>
                    </div>
                    
                    <div>
                        <div class="progress-label">
                            <span>Contexto</span>
                            <span>${formatNumber(session.context_used)}/${formatNumber(session.context_window)}</span>
                        </div>
                        <div class="progress-bar">
                            <div class="progress-fill" style="width: ${(session.context_ratio * 100).toFixed(1)}%"></div>
                        </div>
                    </div>
                    
                    ${session.context_excerpt ? `
                        <div style="margin-top:10px; padding:8px; background: rgba(59,130,246,0.10); border-radius:4px; color:#bfdbfe; font-size:0.82rem;">
                            🧠 Contexto: ${session.context_excerpt}
                        </div>
                    ` : ''}

                    <div style="margin-top:8px; font-size:0.82rem; color:#cbd5e1;">
                        💸 Custo sessão: $${(session.cost_usd || 0).toFixed(4)}
                        ${session.next_action && session.next_action !== '—' ? ` • Próxima ação: ${session.next_action}` : ''}
                        • IA etapa: ${session.lm_status}
                    </div>

                    ${session.error_message ? `
                        <div style="margin-top: 10px; padding: 8px; background: rgba(239, 68, 68, 0.1); border-radius: 4px; color: #fca5a5; font-size: 0.875rem;">
                            ⚠️ ${session.error_message}
                        </div>
                    ` : ''}
                </div>
            `;
        }
        
        function formatNumber(num) {
            if (num >= 1000000) return (num / 1000000).toFixed(1) + 'M';
            if (num >= 1000) return (num / 1000).toFixed(1) + 'K';
            return num.toString();
        }
        
        function formatTime(seconds) {
            const h = Math.floor(seconds / 3600);
            const m = Math.floor((seconds % 3600) / 60);
            const s = seconds % 60;
            if (h > 0) return `${h}h ${m}m`;
            if (m > 0) return `${m}m ${s}s`;
            return `${s}s`;
        }
    </script>
</body>
</html>
"""

MOBILE_HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="pt-BR">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>Monitor Mobile</title>
  <style>
    body { font-family: -apple-system, sans-serif; background:#0f172a; color:#e2e8f0; margin:0; padding:14px; }
    .card { background:#1e293b; border:1px solid #334155; border-radius:10px; padding:12px; margin-bottom:10px; }
    .muted { color:#94a3b8; font-size:12px; }
    .ok { color:#10b981; } .warn { color:#f59e0b; } .err { color:#ef4444; }
  </style>
</head>
<body>
  <h3>📱 Monitor Mobile</h3>
  <div id="summary" class="card muted">Carregando...</div>
  <div id="pending" class="card"></div>
  <div id="sessions"></div>
  <script>
    async function refresh(){
      const r = await fetch('/api/state');
      const s = await r.json();
      document.getElementById('summary').innerHTML = `Sessões: ${s.total_sessions} · Alertas: ${s.alert_count} · Custo: $${s.estimated_cost.toFixed(2)}`;
      document.getElementById('pending').innerHTML = `<b>Pendências</b><br>` + (s.pending_items.length ? s.pending_items.join('<br>') : 'Sem pendências críticas');
      document.getElementById('sessions').innerHTML = s.sessions.map(x => {
        const cls = x.status==='error'?'err':(x.alert_level==='warning'?'warn':'ok');
        return `<div class="card"><div><b>${x.project_name}</b></div><div class="${cls}">${x.status} · ${x.model}</div><div class="muted">Tokens: ${x.tokens_used}/${x.tokens_limit}</div></div>`;
      }).join('');
    }
    refresh(); setInterval(refresh, 3000);
  </script>
</body>
</html>
"""


if __name__ == "__main__":
    import uvicorn
    
    logger.info("Iniciando dashboard na porta 9000...")
    uvicorn.run(app, host="localhost", port=9000)
