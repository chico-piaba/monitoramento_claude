"""Dashboard Web do Monitor Pi Agent + Claude Code."""

import json
import logging
from datetime import datetime
from typing import Dict, List, Optional

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from pi_monitor_core import PiAgentMonitor, SessionMetrics
from pi_monitor_sounds import get_notifier

logger = logging.getLogger(__name__)

# ============================================================================
# MODELOS DE RESPOSTA
# ============================================================================
class SessionView(BaseModel):
    """View simplificada de uma sessão para o frontend."""
    session_id: str
    project_name: str
    source: str  # "pi_agent" ou "claude_code"
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
    
    @staticmethod
    def from_session(session: SessionMetrics) -> "SessionView":
        """Converte SessionMetrics para SessionView."""
        project_name = session.session_id.split(":")[-2] if ":" in session.session_id else "Desconhecido"
        source = "claude_code" if session.provider == "claude_code" else "pi_agent"
        
        return SessionView(
            session_id=session.session_id,
            project_name=project_name,
            source=source,
            model=session.model,
            provider=session.provider,
            status=session.status,
            alert_level=session.alert_level,
            tokens_used=session.tokens_used,
            tokens_limit=session.tokens_limit,
            token_ratio=session.token_ratio,
            context_used=session.context_used,
            context_window=session.context_window,
            context_ratio=session.context_ratio,
            duration_seconds=session.duration_seconds,
            error_message=session.error_message,
            has_subagents=len(session.subagents) > 0,
        )


class DashboardState(BaseModel):
    """Estado completo do dashboard."""
    timestamp: str
    total_sessions: int
    total_tokens_used: int
    estimated_cost: float
    sessions: List[SessionView]
    alert_count: int


# ============================================================================
# APLICAÇÃO FASTAPI
# ============================================================================
app = FastAPI(
    title="Pi Agent + Claude Code Monitor",
    description="Dashboard de monitoramento em tempo real",
)

# Monitor singleton
monitor = PiAgentMonitor()
notifier = get_notifier()

# WebSocket connections
active_connections: List[WebSocket] = []


# ============================================================================
# ROTAS HTTP
# ============================================================================
@app.get("/", response_class=HTMLResponse)
async def dashboard():
    """Retorna o HTML do dashboard."""
    return HTML_TEMPLATE


@app.get("/api/state")
async def get_state() -> DashboardState:
    """Retorna o estado completo do dashboard."""
    sessions = monitor.refresh()
    
    alert_count = sum(
        1 for s in sessions.values()
        if s.alert_level in ("warning", "critical")
    )
    
    return DashboardState(
        timestamp=datetime.now().isoformat(),
        total_sessions=len(sessions),
        total_tokens_used=monitor.get_total_tokens_used(),
        estimated_cost=monitor.get_total_cost_estimate(),
        sessions=[SessionView.from_session(s) for s in sessions.values()],
        alert_count=alert_count,
    )


# ============================================================================
# WEBSOCKET
# ============================================================================
@app.websocket("/ws/monitor")
async def websocket_monitor(websocket: WebSocket):
    """WebSocket para streaming de atualizações em tempo real."""
    await websocket.accept()
    active_connections.append(websocket)
    
    try:
        while True:
            # Aguarda mensagens do cliente (keep-alive)
            try:
                data = await websocket.receive_text()
                # Pode usar para comandos do cliente se necessário
            except WebSocketDisconnect:
                break
            
            # Envia estado atual
            state = await get_state()
            await websocket.send_json(state.dict())
            
            # Aguarda um pouco antes da próxima atualização
            import asyncio
            await asyncio.sleep(2)
    
    finally:
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
            
            // Sessions grid
            const content = document.getElementById('content');
            content.innerHTML = `<div class="sessions-grid">${
                state.sessions.map(renderSession).join('')
            }</div>`;
            
            if (state.sessions.length === 0) {
                content.innerHTML = '<div class="loading"><p>Nenhuma sessão ativa</p></div>';
            }
        }
        
        function renderSession(session) {
            const statusClass = `status-${session.status}`;
            const alertClass = session.alert_level !== 'info' ? `alert-${session.alert_level}` : '';
            const source = session.source === 'claude_code' ? 'claude' : 'pi';
            
            return `
                <div class="session-card ${alertClass}">
                    <div class="session-header">
                        <div class="session-title">
                            <span class="status-indicator ${statusClass}"></span>
                            ${session.project_name}
                            <span class="session-badge ${source}">${source}</span>
                        </div>
                        <div class="session-meta">
                            ${session.model} • ${formatTime(session.duration_seconds)}
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


if __name__ == "__main__":
    import uvicorn
    
    logger.info("Iniciando dashboard na porta 8888...")
    uvicorn.run(app, host="localhost", port=8888)
