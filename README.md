# Monitoramento do Claude Code

Semáforo na bandeja do sistema que mostra o **status da conversa/produção** de
cada sessão (instância) do Claude Code em execução. Cada instância ganha seu
próprio semáforo, e o ícone principal reflete a **última alteração** de status.

## Cores (status da conversa)

| Cor        | Significado                                                        |
|------------|-------------------------------------------------------------------|
| 🟢 Verde   | Produzindo — houve atividade nos últimos segundos                 |
| 🟡 Amarelo | Esperando você — terminou o turno / aguarda input ou decisão      |
| 🔴 Vermelho| Erro, ou parada/travada há muito tempo sem responder              |

O **ícone principal** na bandeja mostra a cor da sessão cujo status mudou mais
recentemente. O **menu** lista todas as instâncias, cada uma com seu semáforo,
estado e há quanto tempo foi o último evento. Uma notificação aparece quando a
cor principal muda.

**Clicar numa instância troca para a janela do VSCode** daquela sessão (foco da
janela via `code <pasta>`). Cada sessão é ligada à sua janela pelos locks de
integração em `~/.claude/ide/*.lock`, casando o `cwd` da sessão com o
`workspaceFolders` da janela.

> Granularidade: o foco é por **janela/workspace**. Se duas sessões rodam na
> mesma janela do VSCode (dois terminais lado a lado), o clique foca a janela,
> mas não dá para escolher o terminal específico — limitação do próprio editor.

## Instalação

```bash
pip install -r requirements.txt
```

## Uso

```bash
# Inicia o app de bandeja
python monitoramento_claude.py

# Lista as instâncias e seus estados no terminal, e sai
python monitoramento_claude.py --check
```

Exemplo de `--check`:

```
4 instância(s) ativa(s):

  🟡 esperando você (   4s)  alece-play-institutional-reduction  <- última alteração
  🟢 produzindo     (   6s)  Finalizar desenvolvimento do monitoramento Claude
  🔴 erro / parada  (  28m)  Revisar estrutura do site

Semáforo principal: 🟡 esperando você
```

## Como funciona

- **Instâncias** = processos `claude` vivos na máquina. Quando o terminal é
  fechado, a instância some da lista.
- Cada processo é mapeado para o transcript da sessão em
  `~/.claude/projects/<projeto>/<sessão>.jsonl`, pela pasta de trabalho (cwd) e
  pelo `.jsonl` modificado mais recentemente.
- O **estado** vem do transcript: horário do último evento e se o turno
  terminou (`stop_reason: end_turn`). Apenas o fim do arquivo é lido, então
  transcripts de dezenas de MB não pesam.
- O título de cada instância vem do `aiTitle` da sessão.

### Limiares (ajustáveis no topo do `.py`)

| Constante         | Padrão | Efeito                                              |
|-------------------|--------|-----------------------------------------------------|
| `VERDE_MAX_S`     | 60 s   | Atividade dentro disso = 🟢 produzindo              |
| `VERMELHO_MIN_S`  | 600 s  | Idle além disso = 🔴 travada/abandonada             |
| `INTERVALO`       | 4 s    | Frequência de verificação                           |

## Notas técnicas

- A detecção de processos usa `psutil` sobre o `argv[0]` (`claude`) e o caminho
  do executável (`~/.local/share/claude/versions/...`), pois o binário é
  versionado e `psutil.name()` retornaria apenas o número da versão.
- O app é puramente baseado em bandeja (sem janela Tkinter): no macOS tanto o
  `pystray` quanto o Tkinter exigem a thread principal e os dois `mainloop` não
  coexistem de forma estável. Todos os detalhes ficam no menu da bandeja.
