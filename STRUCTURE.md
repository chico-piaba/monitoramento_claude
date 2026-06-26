# Estrutura do Projeto - Monitor Pi Agent + Claude Code

```
monitoramento_claude/
│
├── 📄 CONFIGURATION & SETUP
│   ├── pi_monitor_config.py          [Config centralizadas - limites, cores, Sons]
│   ├── requirements.txt               [Dependências Python]
│   ├── quick-start.sh                 [Script de setup automático]
│   └── .gitignore
│
├── 🧠 CORE (Coleta de Dados)
│   ├── pi_monitor_core.py             [Parser unificado PI + Claude Code]
│   │   ├─ UnifiedLogParser
│   │   ├─ SessionMetrics
│   │   ├─ SubagentMetrics
│   │   ├─ Event
│   │   ├─ MetricsStorage (SQLite)
│   │   └─ PiAgentMonitor
│   │
│   └── pi_monitor_claude_code.py      [Parser específico Claude Code]
│       └─ parse_claude_code_transcript()
│
├── 🔔 NOTIFICAÇÕES
│   └── pi_monitor_sounds.py           [Áudio + Notificações]
│       ├─ SoundAlert
│       ├─ NotificationManager
│       ├─ AlertPriority
│       └─ get_notifier() [global]
│
├── 🎨 INTERFACE
│   ├── pi_monitor_dashboard.py        [Web UI - FastAPI + WebSocket]
│   │   ├─ FastAPI app
│   │   ├─ SessionView
│   │   ├─ DashboardState
│   │   ├─ WebSocket /ws/monitor
│   │   └─ HTML_TEMPLATE (dark mode)
│   │
│   └── monitoramento_claude.py        [Bandeja do Sistema]
│       ├─ Semáforo original (mantém compatibilidade)
│       └─ Integração com pi_monitor_sounds
│
├── 🧪 TESTES & UTILIDADES
│   ├── pi_monitor_test.py             [Teste integrado]
│   │   ├─ test_imports()
│   │   ├─ test_monitor()
│   │   ├─ test_sounds()
│   │   ├─ test_database()
│   │   └─ test_notifications()
│   │
│   └── run_all.py                    [Lança dashboard + bandeja]
│
├── 📖 DOCUMENTAÇÃO
│   ├── README_NEW.md                  [Documentação completa]
│   ├── README.md                      [Original - mantém compatibilidade]
│   └── STRUCTURE.md                   [Este arquivo]
│
└── 💾 RUNTIME (criados automaticamente)
    └── ~/.pi_monitor/
        ├── metrics.db                 [Histórico SQLite]
        ├── logs/
        │   └── monitor.log
        └── sounds/
            ├── session_start.mp3
            ├── token_warning.mp3
            ├── context_critical.mp3
            ├── error.mp3
            └── limit_reached.mp3
```

---

## 🔄 Fluxo de Dados

```
┌─────────────────────────────────┐
│ Fontes de Dados                 │
├─────────────────────────────────┤
│ ~/.pi/logs/*.jsonl              │
│ ~/.claude/projects/*/session.jl │
└────────────┬────────────────────┘
             │
             ▼
┌─────────────────────────────────┐
│ UnifiedLogParser                │
├─────────────────────────────────┤
│ _parse_pi_logs()                │
│ _parse_claude_code_sessions()   │
└────────────┬────────────────────┘
             │
             ▼
┌─────────────────────────────────┐
│ SessionMetrics                  │
│ [com análise de alertas]        │
└────────────┬────────────────────┘
             │
     ┌───────┼───────┐
     │       │       │
     ▼       ▼       ▼
   📊      🔔      💾
 Dashboard Sounds  DB
   Web    (notify) (persist)
```

---

## 🚀 Inicialização

### Opção 1: Setup Completo
```bash
./quick-start.sh
```

### Opção 2: Manual
```bash
pip install -r requirements.txt
python3 pi_monitor_dashboard.py      # Terminal 1
python3 monitoramento_claude.py      # Terminal 2
```

### Opção 3: Tudo de Uma Vez
```bash
python3 run_all.py
```

---

## 📊 Arquitetura Detalhada

### Camada 1: Config
- Limiares de alerta
- Limites de tokens por modelo
- Mapeamento de cores/emoji
- Configuração de sons

### Camada 2: Core
- **UnifiedLogParser**: Lê e parseia logs
- **SessionMetrics**: Estrutura de dados
- **MetricsStorage**: Persistência
- **PiAgentMonitor**: Orquestrador

### Camada 3: Notificações
- **SoundAlert**: Reprodução de áudio
- **NotificationManager**: Coordena alertas
- Suporte a afplay (macOS) / paplay (Linux)

### Camada 4: UI
- **Dashboard Web**: FastAPI + WebSocket
- **Bandeja do Sistema**: pystray
- HTML5/CSS3 responsivo

---

## 🔌 APIs

### Core
```python
from pi_monitor_core import PiAgentMonitor

monitor = PiAgentMonitor()
sessions = monitor.refresh()

for session in sessions.values():
    print(f"{session.alert_level}: {session.token_ratio:.1%}")
```

### Sounds
```python
from pi_monitor_sounds import get_notifier

notifier = get_notifier()
notifier.notify_token_warning("session-1", 0.85)
notifier.sound_alert.set_muted(True)
```

### Dashboard
```
GET  /api/state               # Estado completo
WS   /ws/monitor              # Stream em tempo real
GET  /                        # HTML da página
```

---

## 📈 Métricas Coletadas

Por Sessão:
- ✅ session_id, model, provider
- ✅ tokens_used / tokens_limit
- ✅ context_used / context_window
- ✅ status (running, idle, error)
- ✅ alert_level (info, warning, critical)
- ✅ duration, start_time, end_time
- ✅ subagents count + details
- ✅ error_message (se houver)

Por Evento:
- ✅ timestamp, type, level
- ✅ session_id, message
- ✅ details (JSON)

---

## 🎨 Estados e Cores

| Estado | Emoji | Cor     | Significado           |
|--------|-------|---------|----------------------|
| info   | ℹ️    | 🔵 azul | Informativo           |
| running| 🟢    | verde   | Sessão ativa          |
| idle   | 🟡    | amarelo | Esperando interação   |
| warning| ⚠️    | âmbar   | Aviso (80% tokens)    |
| error  | 🔴    | vermelho| Erro                  |
| critical|🚨   | vermelho| Crítico (90%+ tokens) |

---

## 📊 Dashboard Features

- Real-time WebSocket updates
- Responsive grid layout
- Dark mode theme
- Progress bars com cores dinâmicas
- Filter por projeto/source
- Status indicators
- Cost estimation
- Error messages inline

---

## 🔐 Segurança

- ✅ Sem credenciais armazenadas
- ✅ Apenas leitura de arquivos locais
- ✅ SQLite local (sem rede)
- ✅ WebSocket sem autenticação (localhost only)

---

## 📦 Dependências

Core:
- pathlib, json, sqlite3, threading

Web:
- fastapi, uvicorn, socketio, engineio, aiofiles

Desktop:
- pystray, pillow, psutil

---

## 🧪 Testes

```bash
python3 pi_monitor_test.py
```

Testes incluem:
- Imports de módulos
- Parser de logs
- Banco de dados
- Sistema de sons
- Notificações

---

Última atualização: 2026-06-26
