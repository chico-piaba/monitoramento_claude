# Changelog

## 2026-06-26

### Added
- **Monitoramento unificado no tray (Claude + PI)** usando lógica de sessões ativas.
- Menu do tray com novas ações:
  - Abrir dashboard
  - Sync no celular (`/mobile`)
  - Toggle de áudio
  - Teste de áudio
- Dashboard com rota mobile e bloco de pendências.
- Persistência de snapshots do dashboard em SQLite (`dashboard_snapshots`).
- Enriquecimento por sessão ativa com:
  - tokens/contexto
  - custo estimado
  - estágio de trabalho (`stage`) e próxima ação (`next_action`)
- Integração com **LM Studio** para classificação de estágio via `chat/completions`.
- Cache de classificação por transcript (`mtime`) para reduzir chamadas ao LM.

### Changed
- Dashboard passou a consumir a **mesma fonte ativa da tray** (evita backlog/histórico antigo).
- Correção de source badge (`claude` vs `pi`) na UI.
- WebSocket do dashboard ajustado para enviar estado continuamente (sem depender de mensagem do cliente).
- Cálculo de duração no dashboard alterado para usar **tempo no estado atual** (`mudou_em`).
- Regras de estado/pedência refinadas:
  - `needs_attention` sticky até ação do usuário.
  - Notificação quando entra em atenção, mesmo sem troca de cor principal.
- Regras de PI: idle sem erro permanece amarelo (não degrada para vermelho só por timeout).
- `PI_ATIVO_MAX_S` tornou-se configurável por variável de ambiente.

### Fixed
- Detecção de sessões Claude/PI na tray.
- Foco de janela VSCode para PI usando `cwd` real extraído do transcript.
- Semáforo verde/amarelo/vermelho para PI/Claude com parsing compatível de formatos.
- Precificação de sessão PI com fallback (inclusive quando só `tokens_total` existe).

### LM Studio envs
- `LMSTUDIO_BASE` (default: `http://localhost:1234/v1`)
- `LMSTUDIO_MODEL` (default: `gemma-4`)
- `LMSTUDIO_API_KEY`
- `LM_CLASSIFIER_ENABLED` (`1|0`)
- `LM_CLASSIFIER_TIMEOUT_S` (default: `3.0`)
- `LM_CLASSIFY_ONLY_ATTENTION` (`1|0`)

### Notes
- O tray continua como fonte de verdade para instâncias ativas.
- O dashboard agora é observabilidade/gestão (tempo, custo, etapa, pendências), sem automação de browser/puppeteering.
