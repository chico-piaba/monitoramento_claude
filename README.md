# Monitoramento Claude + PI (Tray + Dashboard)

Sistema de observabilidade local para sessões **ativas** do Claude Code e PI Agent:

- 📍 **Tray (semáforo)** para troca rápida de contexto
- 📊 **Dashboard web** com status, pendências, tokens, custo e etapa
- 🔔 **Áudio/notificação** quando entra em estado de atenção
- 📱 **Visão mobile** (`/mobile`)

> Foco: observabilidade e gestão de execução (tempo, custo, estágio, pendências). Sem puppeteering.

---

## 1) Componentes

## Tray (`monitoramento_claude.py`)
- Monitora instâncias ativas de:
  - Claude (por processo vivo)
  - PI (por atividade recente do transcript)
- Semáforo por sessão:
  - 🟢 produzindo
  - 🟡 aguardando você / idle
  - 🔴 erro crítico
- Clique na sessão tenta focar a janela do VSCode (`code <workspace>`)
- Menu extra:
  - Abrir dashboard
  - Sync no celular
  - Áudio on/off
  - Teste de áudio

## Dashboard (`pi_monitor_dashboard.py`)
- Fonte de verdade: **snapshot da tray ativa** (evita backlog antigo)
- Mostra por sessão:
  - status
  - contexto resumido
  - tokens/contexto
  - custo estimado
  - estágio (`stage`) + próxima ação (`next_action`)
- Endpoints:
  - `/` dashboard principal
  - `/mobile` versão compacta
  - `/api/state` JSON
  - `/ws/monitor` stream em tempo real

---

## 2) Instalação

```bash
cd /Users/rodrigolima/Documents/AI-ASSISTANT/PROJETOS/monitoramento_claude
pip3 install -r requirements.txt
```

---

## 3) Uso local

## Checar sessões ativas
```bash
python3 monitoramento_claude.py --check
```

## Iniciar tray
```bash
python3 monitoramento_claude.py
```

## Iniciar dashboard
```bash
python3 pi_monitor_dashboard.py
# abre em http://localhost:9000
```

## Reinício rápido
```bash
pkill -f monitoramento_claude.py || true
pkill -f pi_monitor_dashboard.py || true
python3 monitoramento_claude.py
python3 pi_monitor_dashboard.py
```

---

## 4) LM Studio (classificação de etapa)

Compatível com LM Studio local (OpenAI-like).

Variáveis:

```bash
export LMSTUDIO_BASE="http://localhost:1234/v1"
export LMSTUDIO_MODEL="gemma-4"
export LMSTUDIO_API_KEY="<token>"

export LM_CLASSIFIER_ENABLED=1
export LM_CLASSIFY_ONLY_ATTENTION=1
export LM_CLASSIFIER_TIMEOUT_S=3.0

# opcional: override completo do endpoint
export LMSTUDIO_CHAT_URL=""
```

Fallback de endpoint automático:
- `.../chat/completions`
- `.../responses`

Se LM falhar, cai em heurística local (sem quebrar painel).

---

## 5) Docker / CI

Arquivos:
- `Dockerfile`
- `.github/workflows/build-docker.yml`

Build local:
```bash
docker build -t monitoramento-claude:local .
docker run --rm -p 9000:9000 monitoramento-claude:local
```

> Em container/headless, o módulo da tray não derruba o processo (pystray é tratado com fallback).

---

## 6) Configuração importante

No tray:
- `PI_ATIVO_MAX_S` (default `1800`): janela de atividade do PI para não “sumir” em idle.

Exemplo:
```bash
PI_ATIVO_MAX_S=1800 python3 monitoramento_claude.py
```

Regras de estado PI:
- idle sem erro => 🟡
- erro real => 🔴

---

## 7) Persistência

Snapshots do dashboard em SQLite:
- `~/.pi_monitor/metrics.db`
- tabela `dashboard_snapshots`

---

## 8) Troubleshooting rápido

### Dashboard não carrega
- confirme processo:
```bash
lsof -i :9000
```
- hard refresh no browser: `Cmd+Shift+R`

### PI sumiu
- aumentar `PI_ATIVO_MAX_S`
- validar com `--check`

### LM Studio erro de endpoint
- use `LMSTUDIO_CHAT_URL` ou deixe fallback automático
- confirme auth local

---

## 9) Changelog

Veja `CHANGELOG.md` para histórico detalhado das implementações.
