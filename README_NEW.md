# Monitor Pi Agent + Claude Code 🚀

Sistema avançado de monitoramento em tempo real para **pi agent** e **Claude Code** com:

- 📊 **Dashboard web arrojado** com visualização de sessões, tokens e contexto
- 🔔 **Notificações sonoras** para eventos críticos
- ⚠️ **Alertas inteligentes** para estouro de contexto e limites de tokens
- 👥 **Rastreamento de subagents** (colony, swarms, etc)
- 💰 **Estimativa de custo** por sessão
- 📱 **Bandeja do sistema** com semáforos por instância
- 🎯 **Suporte para ambos** pi agent (~/.pi/logs) e Claude Code (~/.claude/projects)

---

## 🎯 Arquitetura

```
pi_monitor_config.py          # Configurações centralizadas
│
├─ pi_monitor_core.py         # Parser unificado de logs
│  ├─ Pi Agent logs           # ~/.pi/logs/*.jsonl
│  └─ Claude Code transcripts # ~/.claude/projects/*/[session].jsonl
│
├─ pi_monitor_claude_code.py  # Parser específico Claude Code
├─ pi_monitor_sounds.py       # Sistema de áudio + notificações
├─ pi_monitor_dashboard.py    # Dashboard web (FastAPI + WebSocket)
│
└─ monitoramento_claude.py    # Semáforo na bandeja (mantém compatibilidade)
```

---

## 📊 Funcionalidades Principais

### 1. **Coleta de Métricas** (Core)

```python
from pi_monitor_core import PiAgentMonitor

monitor = PiAgentMonitor()
sessions = monitor.refresh()

for session_id, session in sessions.items():
    print(f"{session_id}: {session.token_ratio:.1%} tokens")
    print(f"  Status: {session.alert_level}")  # info, warning, critical
    print(f"  Modelo: {session.model}")
    print(f"  Subagents: {len(session.subagents)}")
```

**Detecta automaticamente:**
- ✅ Sessões pi agent (~/.pi/logs)
- ✅ Sessões Claude Code (~/.claude/projects)
- ✅ Tokens usados (input + output)
- ✅ Status (running, idle, error)
- ✅ Subagents (colony, swarms, cascade)

### 2. **Notificações Sonoras**

```python
from pi_monitor_sounds import get_notifier

notifier = get_notifier()

# Eventos automáticos
notifier.notify_token_warning(session_id, 0.82)      # Amarelo
notifier.notify_context_critical(session_id, 0.91)   # Vermelho
notifier.notify_error(session_id, "Model timeout")   # Crítico
```

**Sons personalizáveis:**
- 🔔 `session_start` - Sessão iniciada (baixo volume)
- ⚠️ `token_warning` - 80% de tokens (médio)
- 🚨 `context_critical` - 90% de contexto (alto)
- ❌ `error` - Erro ou falha (crítico)
- 🛑 `limit_reached` - Limite atingido (crítico)

### 3. **Dashboard Web**

Acesse **http://localhost:8888** para:

- 📈 **Gráficos de tokens** em tempo real
- 📊 **Status de subagents** com semáforo
- 💾 **Histórico de eventos** (6h rolling window)
- 💰 **Custo estimado** por sessão/período
- 🎯 **Filtros** por projeto, modelo, provider

**Atualização em tempo real via WebSocket**

### 4. **Bandeja do Sistema**

Mantém compatibilidade com o monitor original:

```bash
python monitoramento_claude.py              # Inicia semáforo na bandeja
python monitoramento_claude.py --check      # Imprime estado e sai
```

---

## 🚀 Instalação

### Dependências

```bash
pip install -r requirements.txt
```

**Requisitos:**
- Python 3.9+
- macOS (para afplay/osascript) ou Linux (paplay)
- Acesso a ~/.pi/logs e ~/.claude/projects

### Setup

```bash
# Clone ou navegue até o diretório
cd /Users/rodrigolima/Documents/AI-ASSISTANT/PROJETOS/monitoramento_claude

# Instale dependências
pip install -r requirements.txt

# Execute o dashboard
python pi_monitor_dashboard.py

# Em outro terminal: Execute o semáforo na bandeja
python monitoramento_claude.py
```

---

## 📖 Uso

### Dashboard Web

```bash
python pi_monitor_dashboard.py
# Acesse http://localhost:8888
```

**Features:**
- Stats em tempo real (total de tokens, custo, alertas)
- Cards por sessão com barras de progresso
- Indicadores visuais de alerta (cores)
- Filtros por projeto/fonte
- Download de histórico (em breve)

### Monitoramento Programático

```python
from pi_monitor_core import PiAgentMonitor
from pi_monitor_sounds import get_notifier

monitor = PiAgentMonitor()
notifier = get_notifier()

while True:
    sessions = monitor.refresh()
    
    for session_id, session in sessions.items():
        # Alerta se tokens ultrapassarem 80%
        if session.token_ratio > 0.80:
            notifier.notify_token_warning(session_id, session.token_ratio)
        
        # Alerta crítico se contexto > 90%
        if session.context_ratio > 0.90:
            notifier.notify_context_critical(session_id, session.context_ratio)
        
        # Alerta se erro
        if session.status == "error":
            notifier.notify_error(session_id, session.error_message)
    
    time.sleep(4)  # Verificar a cada 4 segundos
```

### Customização

**Configurar limiares** em `pi_monitor_config.py`:

```python
@dataclass
class TokenThresholds:
    warning: float = 0.80      # 🟡 Amarelo
    critical: float = 0.90     # 🔴 Vermelho
    hard_limit: float = 0.99   # 🛑 Bloqueio

@dataclass
class ContextThresholds:
    warning: float = 0.75      # Contexto em risco
    critical: float = 0.90     # Contexto crítico
```

**Mutar sons:**

```python
from pi_monitor_sounds import get_notifier

notifier = get_notifier()
notifier.sound_alert.set_muted(True)        # Muta todos
notifier.sound_alert.set_volume(0.5)        # 50% volume
notifier.sound_alert.toggle_mute_category("token_warning")  # Muta 1 categoria
```

---

## 🎨 Visualização

### Dashboard Web

```
┌─────────────────────────────────────────────────────┐
│ 🚀 Monitor Pi Agent + Claude Code                   │
├─────────────────────────────────────────────────────┤
│ Sessões Ativas: 3    Tokens: 120K    Custo: $12.34 │
├─────────────────────────────────────────────────────┤
│                                                      │
│  ┌─────────────────┐  ┌─────────────────┐          │
│  │ 🟢 PI Agent     │  │ 🟡 Claude Code  │          │
│  │ claude-3.5      │  │ sonnet          │          │
│  │ Tokens: 45K/200K│  │ Tokens: 75K/200K│         │
│  │ ████░░░░░░░░░░ │  │ ██████░░░░░░░░░ │         │
│  │ 22%             │  │ 37%             │         │
│  └─────────────────┘  └─────────────────┘          │
│                                                      │
│  ┌─────────────────┐                               │
│  │ 🔴 ERROR        │                               │
│  │ gpt-4           │                               │
│  │ Context limit!  │                               │
│  └─────────────────┘                               │
│                                                      │
└─────────────────────────────────────────────────────┘
```

### Bandeja do Sistema

```
🟢 Último: Claude Code (5s)
├─ 🟢 Produzindo (45s)  - pi-agent
├─ 🟡 Esperando (120s)  - claude-code
└─ 🔴 Erro (15m)        - gpt-4
```

---

## 📊 Estrutura de Dados

### SessionMetrics

```python
@dataclass
class SessionMetrics:
    session_id: str           # "pi:xyz" ou "claude-code:proj:xyz"
    start_time: datetime
    model: str                # "claude-3-5-sonnet"
    provider: str             # "claude_code", "pi_agent"
    status: str               # "running", "idle", "error"
    tokens_used: int          # Total consumido
    tokens_limit: int         # Limite do modelo
    context_used: int         # Tokens do contexto
    context_window: int       # Janela de contexto
    subagents: [SubagentMetrics]  # Instâncias filhas
    events: [Event]           # Histórico de eventos
```

### SubagentMetrics

```python
@dataclass
class SubagentMetrics:
    id: str
    type: str                 # "colony", "swarm", "nested"
    status: str
    tokens_used: int
    tokens_limit: int
```

---

## ⚙️ Configuração Avançada

### Limites de Alerta

```python
# pi_monitor_config.py
TOKEN_THRESHOLDS = TokenThresholds(
    warning=0.80,      # 80% = amarelo
    critical=0.90,     # 90% = vermelho
    hard_limit=0.99,   # 99% = bloqueio
)

CONTEXT_THRESHOLDS = ContextThresholds(
    warning=0.75,      # 75% = aviso
    critical=0.90,     # 90% = crítico
)
```

### Sons Personalizados

Adicione seus arquivos `.mp3` em `~/.pi_monitor/sounds/`:

```python
SOUND_EVENTS = {
    "session_start": {
        "file": "bell_start.mp3",
        "volume": 0.5,
        "priority": "low",
    },
    # ... etc
}
```

### Custo Estimado

Configurar rates por provider em `pi_monitor_config.py`:

```python
RATES_PER_MILLION = {
    "claude": {"input": 3.0, "output": 15.0},
    "gpt-4": {"input": 30.0, "output": 60.0},
    "gpt-3.5": {"input": 0.5, "output": 1.5},
}
```

---

## 🧪 Testes

```bash
# Test core parsing
python -m pi_monitor_core

# Test dashboard
python pi_monitor_dashboard.py

# Test sounds
python -c "from pi_monitor_sounds import get_notifier; get_notifier().notify_token_warning('test', 0.85)"

# Test em tempo real
python pi_monitor_tester.py
```

---

## 📝 Logs

Logs salvos em `~/.pi_monitor/logs/monitor.log`:

```
[2026-06-26 15:23:45] INFO - pi_monitor_core - Sessões encontradas: 3
[2026-06-26 15:23:45] WARNING - pi_monitor_sounds - Token warning para pi:xyz: 82%
[2026-06-26 15:24:10] ERROR - pi_monitor_core - Context critical para claude-code:proj:abc: 91%
```

---

## 🔮 Roadmap

- [ ] Histórico persistente em SQLite (24h)
- [ ] Download de CSV com métricas
- [ ] Gráficos de custo ao longo do tempo
- [ ] Alertas via Slack/Discord/Email
- [ ] API de webhook para eventos
- [ ] Mobile app (React Native)
- [ ] Dark/Light theme toggle
- [ ] Multi-user com autenticação

---

## 🐛 Troubleshooting

### Dashboard não abre
```bash
# Verifique porta 8888
lsof -i :8888

# Ou use outra porta
python pi_monitor_dashboard.py --port 9999
```

### Sons não funcionam
```bash
# Teste afplay (macOS)
afplay /System/Library/Sounds/Glass.aiff

# Ou use síntese de voz
say "Test"
```

### Logs não aparecem
```bash
# Verifique diretório
ls -la ~/.pi_monitor/logs/

# Ou crie manualmente
mkdir -p ~/.pi_monitor/logs
```

---

## 📄 Licença

MIT - Use livremente!

---

## 💬 Feedback

Contribuições bem-vindas! Abra uma issue ou PR.

```bash
git add -A
git commit -m "Minha melhoria"
git push origin feature/my-feature
```

---

## Últimas Atualizações

- ✅ Parser unificado para Pi Agent + Claude Code
- ✅ Dashboard web com WebSocket
- ✅ Sistema de sons adaptativo
- ✅ Suporte a subagents (colony, swarms)
- ✅ Estimativa de custo

Próximo: Histórico persistente + Gráficos temporais 📊
