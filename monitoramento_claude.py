"""Monitoramento do Claude Code — semáforo por instância na bandeja.

Cada sessão (instância) do Claude Code em execução ganha seu próprio semáforo,
baseado no estado da conversa/produção:

    🟢 verde    -> produzindo (houve atividade nos últimos segundos)
    🟡 amarelo  -> terminou o turno / está te esperando (precisa de input ou decisão)
    🔴 vermelho -> erro, ou parada/travada há muito tempo sem responder

O ícone principal na bandeja mostra a cor da ÚLTIMA ALTERAÇÃO — ou seja, a cor
da sessão que mudou de status mais recentemente. O menu lista todas as
instâncias, cada uma com seu próprio semáforo.

Como funciona a detecção:
  - As instâncias são os processos `claude` vivos na máquina.
  - Cada processo é mapeado para o transcript da sessão (~/.claude/projects/...)
    pela pasta de trabalho (cwd) e pelo .jsonl modificado mais recentemente.
  - O estado vem do transcript: horário do último evento + se o turno terminou.

Uso:
    python monitoramento_claude.py          # inicia o app de bandeja
    python monitoramento_claude.py --check   # imprime as instâncias e sai
"""

import os
import re
import sys
import glob
import json
import time
import shutil
import threading
import subprocess
import webbrowser
import socket
from datetime import datetime

import psutil
from pystray import Icon, Menu, MenuItem
from PIL import Image, ImageDraw

# --- Parâmetros de tempo -----------------------------------------------------
INTERVALO = 4            # segundos entre verificações
VERDE_MAX_S = 60         # atividade dentro disso = produzindo (verde)
VERMELHO_MIN_S = 600     # idle além disso = travada/abandonada (vermelho)

# --- Identificação do binário do Claude Code ---------------------------------
# O executável é versionado (~/.local/share/claude/versions/2.1.193), então
# psutil.name() retorna a versão. Detecta-se por argv[0] (sempre "claude") e/ou
# pelo caminho do executável.
NOME_CLAUDE = "claude"
MARCADOR_EXE = os.path.join("claude", "versions")

DIR_PROJETOS = os.path.expanduser("~/.claude/projects")
DIR_IDE_LOCKS = os.path.expanduser("~/.claude/ide")
DIR_PI_SESSOES = os.path.expanduser("~/.pi/agent/sessions")
PI_ATIVO_MAX_S = int(os.getenv("PI_ATIVO_MAX_S", "180"))  # sessão pi ativa por janela de atualização
DASHBOARD_URL = "http://localhost:9000"
AUDIO_ENABLED = True

# Binário do VSCode para focar a janela (clicar numa instância "troca de janela").
# Quando o app é aberto pelo Finder o PATH pode não ter /usr/local/bin, então
# tentamos localizações conhecidas além do which.
CODE_BIN = (
    shutil.which("code")
    or next((c for c in ("/usr/local/bin/code", "/opt/homebrew/bin/code") if os.path.exists(c)), None)
)

# --- Cores e textos ----------------------------------------------------------
CORES = {
    "green": (40, 167, 69),
    "yellow": (255, 193, 7),
    "red": (220, 53, 69),
}
EMOJI = {"green": "🟢", "yellow": "🟡", "red": "🔴"}
ESTADO_TEXTO = {
    "green": "produzindo",
    "yellow": "esperando você",
    "red": "erro / parada",
}


# ---------------------------------------------------------------------------
# Processos e mapeamento para transcripts
# ---------------------------------------------------------------------------
def processos_claude():
    """Itera os processos `claude` vivos (exceto este monitor)."""
    eu = os.getpid()
    for proc in psutil.process_iter(["pid", "cmdline", "exe"]):
        try:
            if proc.info["pid"] == eu:
                continue
            cmdline = proc.info.get("cmdline") or []
            argv0 = os.path.basename(cmdline[0]) if cmdline else ""
            exe = proc.info.get("exe") or ""
            if argv0 == NOME_CLAUDE or MARCADOR_EXE in exe:
                yield proc
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            continue


def projeto_dir(cwd):
    """Converte um cwd no diretório de transcripts correspondente."""
    return os.path.join(DIR_PROJETOS, re.sub(r"[^A-Za-z0-9]", "-", cwd))


def carregar_workspaces():
    """Lê os locks da integração com o VSCode e retorna os workspaceFolders."""
    folders = []
    for f in glob.glob(os.path.join(DIR_IDE_LOCKS, "*.lock")):
        try:
            with open(f) as fh:
                dados = json.load(fh)
        except (OSError, json.JSONDecodeError):
            continue
        for w in dados.get("workspaceFolders") or []:
            folders.append(w)
    return folders


def resolver_workspace(cwd, folders):
    """Encontra a janela do VSCode (workspace) que contém o cwd da sessão.

    Casa o cwd com o workspaceFolder igual ou ancestral mais específico. Se nada
    casar, devolve o próprio cwd (o `code` ainda foca a janela se ela existir).
    """
    melhor = None
    for w in folders:
        base = w.rstrip("/")
        if cwd == w or cwd.startswith(base + "/"):
            if melhor is None or len(base) > len(melhor):
                melhor = base
    return melhor or cwd


def focar_janela(workspace):
    """Traz a janela do VSCode daquele workspace para frente ('troca de janela')."""
    if not CODE_BIN:
        print("VSCode CLI ('code') não encontrado.", file=sys.stderr)
        return
    try:
        # `code <pasta>` foca a janela já aberta com essa pasta (sem duplicar).
        subprocess.Popen(
            [CODE_BIN, workspace],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except Exception as exc:
        print(f"Falha ao focar a janela: {exc}", file=sys.stderr)


def caminhos_instancias_claude():
    """Retorna [(jsonl, cwd, fonte)] das sessões *ativas* do Claude (por processo vivo)."""
    por_cwd = {}
    for proc in processos_claude():
        try:
            cwd = proc.cwd()
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
        por_cwd[cwd] = por_cwd.get(cwd, 0) + 1

    instancias = []
    for cwd, n in por_cwd.items():
        pasta = projeto_dir(cwd)
        if not os.path.isdir(pasta):
            continue
        jsonls = glob.glob(os.path.join(pasta, "*.jsonl"))
        jsonls.sort(key=lambda p: os.path.getmtime(p), reverse=True)
        for j in jsonls[:n]:
            instancias.append((j, cwd, "claude"))
    return instancias


def caminhos_instancias_pi(agora=None):
    """Retorna [(jsonl, pseudo_cwd, fonte)] de sessões *recentes* do pi agent.

    Como o pi nem sempre tem um processo fácil de identificar aqui, usamos um
    critério robusto de atividade: transcript atualizado nos últimos PI_ATIVO_MAX_S.
    """
    if agora is None:
        agora = time.time()
    if not os.path.isdir(DIR_PI_SESSOES):
        return []

    instancias = []
    for pasta in glob.glob(os.path.join(DIR_PI_SESSOES, "*")):
        if not os.path.isdir(pasta):
            continue
        jsonls = glob.glob(os.path.join(pasta, "*.jsonl"))
        if not jsonls:
            continue
        mais_recente = max(jsonls, key=os.path.getmtime)
        mtime = os.path.getmtime(mais_recente)
        if agora - mtime <= PI_ATIVO_MAX_S:
            pseudo_cwd = os.path.basename(pasta)
            instancias.append((mais_recente, pseudo_cwd, "pi"))
    return instancias


def caminhos_instancias():
    """Instâncias ativas combinadas (Claude por processo + pi por atividade recente)."""
    agora = time.time()
    return caminhos_instancias_claude() + caminhos_instancias_pi(agora=agora)


# ---------------------------------------------------------------------------
# Leitura e interpretação do transcript
# ---------------------------------------------------------------------------
def ler_cauda(path, nbytes=65536):
    """Lê apenas o fim do arquivo (transcripts podem ter dezenas de MB)."""
    with open(path, "rb") as f:
        f.seek(0, os.SEEK_END)
        tamanho = f.tell()
        f.seek(max(0, tamanho - nbytes))
        dados = f.read()
    linhas = dados.decode("utf-8", "ignore").splitlines()
    if tamanho > nbytes and linhas:
        linhas = linhas[1:]  # descarta a primeira linha (possivelmente parcial)
    return linhas


def ler_cabeca(path, nbytes=32768):
    """Lê o início do arquivo (útil para metadados como cwd no pi)."""
    with open(path, "rb") as f:
        dados = f.read(nbytes)
    return dados.decode("utf-8", "ignore").splitlines()


def _parse_ts(s):
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return None


def obter_cwd_pi(path):
    """Extrai o cwd real de um transcript do pi (evento type=session)."""
    try:
        for ln in ler_cabeca(path, nbytes=32768):
            try:
                o = json.loads(ln)
            except json.JSONDecodeError:
                continue
            if o.get("type") == "session" and o.get("cwd"):
                return o.get("cwd")
    except OSError:
        return None
    return None


def analisar_sessao(path):
    """Extrai do transcript sinais para decidir cor e pendência de atenção humana."""
    info = {
        "titulo": None,
        "last_prompt": None,
        "last_ts": None,
        "end_turn": False,
        "erro": False,
        "needs_attention": False,
        "attention_since": None,
        "attention_reason": None,  # end_turn | error
    }

    last_user_ts = None
    attention_ts = None
    attention_reason = None

    for ln in ler_cauda(path):
        try:
            o = json.loads(ln)
        except json.JSONDecodeError:
            continue
        tipo = o.get("type")

        if tipo == "ai-title" and o.get("aiTitle"):
            info["titulo"] = o["aiTitle"]
        elif tipo == "last-prompt" and o.get("lastPrompt"):
            info["last_prompt"] = o["lastPrompt"]
        elif tipo in ("assistant", "user", "message"):
            msg = o.get("message") or {}
            ts = _parse_ts(o.get("timestamp")) or _parse_ts(msg.get("timestamp"))
            if ts is None:
                continue

            info["last_ts"] = ts
            role = msg.get("role")
            stop_reason = msg.get("stop_reason") or msg.get("stopReason")

            # Usuário respondeu: limpa pendência anterior.
            if role == "user":
                last_user_ts = ts

            # Assistant finalizou turno => normalmente aguarda usuário.
            if role == "assistant" and stop_reason in ("end_turn", "endTurn"):
                attention_ts = ts
                attention_reason = "end_turn"

            # Erros de ferramenta (Claude e pi) => requer atenção humana.
            erro = False
            content = msg.get("content")
            if isinstance(content, list):
                for c in content:
                    if isinstance(c, dict) and c.get("type") == "tool_result" and c.get("is_error"):
                        erro = True
            if role == "toolResult" and (msg.get("isError") or msg.get("is_error")):
                erro = True
            if erro:
                attention_ts = ts
                attention_reason = "error"

            info["erro"] = erro
            info["end_turn"] = role == "assistant" and stop_reason in ("end_turn", "endTurn")

    # Pendência é "sticky" até usuário mandar nova mensagem após a pendência.
    if attention_ts is not None and (last_user_ts is None or last_user_ts < attention_ts):
        info["needs_attention"] = True
        info["attention_since"] = attention_ts
        info["attention_reason"] = attention_reason

    return info


def estado_cor(info, agora):
    """Mapeia os sinais da sessão para verde / amarelo / vermelho."""
    if info["last_ts"] is None:
        return "yellow"

    # Se precisa de atenção humana, não volta para verde sozinho.
    if info.get("needs_attention"):
        base_ts = info.get("attention_since") or info["last_ts"]
        idade = agora - base_ts
        if info.get("attention_reason") == "error":
            return "red"
        return "yellow" if idade < VERMELHO_MIN_S else "red"

    idade = agora - info["last_ts"]
    if idade < VERDE_MAX_S:
        return "green"
    if idade < VERMELHO_MIN_S:
        return "yellow"
    return "red"


def formatar_duracao(segundos):
    segundos = int(max(0, segundos))
    horas, resto = divmod(segundos, 3600)
    minutos, seg = divmod(resto, 60)
    if horas:
        return f"{horas}h {minutos}m"
    if minutos:
        return f"{minutos}m"
    return f"{seg}s"


# ---------------------------------------------------------------------------
# Ícones do semáforo principal
# ---------------------------------------------------------------------------
def criar_icone(cor):
    tamanho = 64
    imagem = Image.new("RGBA", (tamanho, tamanho), (0, 0, 0, 0))
    draw = ImageDraw.Draw(imagem)
    draw.ellipse((6, 6, tamanho - 6, tamanho - 6), fill=CORES[cor])
    return imagem


ICONES = {estado: criar_icone(estado) for estado in CORES}


# ---------------------------------------------------------------------------
# Monitor: coleta as instâncias e rastreia a "última alteração"
# ---------------------------------------------------------------------------
class Monitor:
    def __init__(self):
        self.lock = threading.Lock()
        self.instancias = []          # snapshot atual (lista de dicts)
        self.estados = {}             # sid -> {"cor": str, "mudou_em": float}
        self.ultima_alteracao = None  # sid da última alteração
        self.ultima_checagem = None

    def coletar(self):
        agora = time.time()
        workspaces = carregar_workspaces()
        atuais = []
        for path, cwd, fonte in caminhos_instancias():
            try:
                info = analisar_sessao(path)
            except OSError:
                continue

            cwd_real = cwd
            if fonte == "pi":
                cwd_extraido = obter_cwd_pi(path)
                if cwd_extraido:
                    cwd_real = cwd_extraido

            sid_base = os.path.basename(path)[:-6]  # remove ".jsonl"
            sid = f"{fonte}:{sid_base}"
            cor = estado_cor(info, agora)
            # Regra específica do PI: se ficou idle sem erro, mantém amarelo
            # (não degrada para vermelho apenas por tempo).
            if fonte == "pi" and cor == "red" and not info.get("erro"):
                cor = "yellow"
            titulo_base = info["titulo"] or os.path.basename(cwd_real) or sid_base[:8]
            prefixo = "[PI]" if fonte == "pi" else "[Claude]"
            titulo = f"{prefixo} {titulo_base}"
            workspace = resolver_workspace(cwd_real, workspaces)
            atuais.append(
                {
                    "sid": sid,
                    "fonte": fonte,
                    "cor": cor,
                    "titulo": titulo,
                    "projeto": os.path.basename(cwd_real) or cwd_real,
                    "workspace": workspace,
                    "last_ts": info["last_ts"] or os.path.getmtime(path),
                    "last_prompt": info["last_prompt"],
                    "transcript_path": path,
                    "needs_attention": bool(info.get("needs_attention")),
                    "attention_reason": info.get("attention_reason"),
                }
            )

        with self.lock:
            for inst in atuais:
                anterior = self.estados.get(inst["sid"])
                if anterior is None:
                    # Sessão nova: ancora a "mudança" na sua última atividade,
                    # para que a mais recente vire principal já na 1ª pintura.
                    mudou = inst["last_ts"] or agora
                elif anterior["cor"] != inst["cor"]:
                    mudou = agora                      # mudança de estado real
                else:
                    mudou = anterior["mudou_em"]
                self.estados[inst["sid"]] = {"cor": inst["cor"], "mudou_em": mudou}
                inst["mudou_em"] = mudou

            # Descarta estados de sessões que não existem mais.
            vivos = {i["sid"] for i in atuais}
            self.estados = {k: v for k, v in self.estados.items() if k in vivos}

            if atuais:
                principal = max(atuais, key=lambda i: i["mudou_em"])
                self.ultima_alteracao = principal["sid"]
            else:
                self.ultima_alteracao = None

            self.instancias = atuais
            self.ultima_checagem = agora

    def snapshot(self):
        with self.lock:
            return list(self.instancias), self.ultima_alteracao, self.ultima_checagem

    def cor_principal(self):
        instancias, alt, _ = self.snapshot()
        if not instancias:
            return "yellow"
        for inst in instancias:
            if inst["sid"] == alt:
                return inst["cor"]
        return instancias[0]["cor"]


monitor = Monitor()


# ---------------------------------------------------------------------------
# Menu da bandeja
# ---------------------------------------------------------------------------
def _linha_principal():
    instancias, alt, _ = monitor.snapshot()
    if not instancias:
        return "Nenhuma instância ativa (Claude/PI)"
    for inst in instancias:
        if inst["sid"] == alt:
            return f"Última alteração: {EMOJI[inst['cor']]} {inst['titulo']}"
    return "Instâncias ativas (Claude/PI)"


def _texto_ultima_checagem(item=None):
    _, _, ultima = monitor.snapshot()
    if ultima is None:
        return "Última verificação: —"
    return "Última verificação: " + time.strftime("%H:%M:%S", time.localtime(ultima))


def _acao_focar(workspace):
    """Cria o callback de clique que foca a janela do workspace informado."""
    return lambda icon, item: focar_janela(workspace)


def _abrir_dashboard(icon=None, item=None):
    try:
        webbrowser.open(DASHBOARD_URL)
    except Exception as exc:
        print(f"Falha ao abrir dashboard: {exc}", file=sys.stderr)


def _descobrir_ip_local():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "localhost"


def _sincronizar_celular(icon=None, item=None):
    ip = _descobrir_ip_local()
    url = f"http://{ip}:9000/mobile"
    try:
        webbrowser.open(url)
        try:
            icon.notify(f"Abra no celular: {url}", "Sync celular")
        except Exception:
            pass
    except Exception as exc:
        print(f"Falha ao abrir sync mobile: {exc}", file=sys.stderr)


def _alternar_audio(icon=None, item=None):
    global AUDIO_ENABLED
    AUDIO_ENABLED = not AUDIO_ENABLED


def _teste_audio(icon=None, item=None):
    if not AUDIO_ENABLED:
        return
    try:
        subprocess.Popen(["afplay", "/System/Library/Sounds/Glass.aiff"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception:
        print("\a", end="", flush=True)


def construir_menu():
    instancias, _, _ = monitor.snapshot()
    agora = time.time()

    itens = [MenuItem(_linha_principal(), None, enabled=False), Menu.SEPARATOR]

    if not instancias:
        itens.append(MenuItem("— nenhuma sessão ativa —", None, enabled=False))
    else:
        # Mais recentemente alterada no topo. Clicar foca a janela do VSCode.
        for inst in sorted(instancias, key=lambda i: i.get("mudou_em", 0), reverse=True):
            idade = formatar_duracao(agora - inst["last_ts"]) if inst["last_ts"] else "?"
            rotulo = (
                f"{EMOJI[inst['cor']]} {inst['titulo']}  "
                f"·  {ESTADO_TEXTO[inst['cor']]} ({idade})"
            )
            ws = inst.get("workspace")
            itens.append(MenuItem(rotulo, _acao_focar(ws), enabled=bool(ws)))

    itens += [
        Menu.SEPARATOR,
        MenuItem(_texto_ultima_checagem, None, enabled=False),
        MenuItem("Atualizar agora", lambda icon, item: checar(icon)),
        MenuItem("Abrir dashboard", _abrir_dashboard),
        MenuItem("Sync no celular", _sincronizar_celular),
        MenuItem(lambda item: f"Áudio: {'ligado' if AUDIO_ENABLED else 'desligado'}", _alternar_audio),
        MenuItem("Testar áudio", _teste_audio),
        Menu.SEPARATOR,
        MenuItem("Sair", lambda icon, item: icon.stop()),
    ]
    return Menu(*itens)


# ---------------------------------------------------------------------------
# Loop de monitoramento
# ---------------------------------------------------------------------------
def checar(icon):
    antes, _, _ = monitor.snapshot()
    attention_antes = {i["sid"]: bool(i.get("needs_attention")) for i in antes}
    cor_anterior = monitor.cor_principal()

    try:
        monitor.coletar()
    except Exception as exc:  # nunca deixa o loop morrer
        print(f"Erro no monitoramento: {exc}", file=sys.stderr)

    cor = monitor.cor_principal()
    instancias, _, _ = monitor.snapshot()

    icon.icon = ICONES[cor]
    qt_pi = sum(1 for i in instancias if i.get("fonte") == "pi")
    qt_claude = sum(1 for i in instancias if i.get("fonte") == "claude")
    icon.title = (
        f"Monitor: {len(instancias)} · Claude {qt_claude} · PI {qt_pi} "
        f"· principal {EMOJI[cor]}"
    )
    icon.menu = construir_menu()
    icon.update_menu()

    # Notificação quando status principal muda.
    if cor != cor_anterior:
        try:
            icon.notify(f"Status principal: {ESTADO_TEXTO[cor]}", "Monitoramento Claude + PI")
        except Exception:
            pass
        if AUDIO_ENABLED:
            _teste_audio()

    # Notificação de pendência nova (precisa de você), mesmo sem trocar cor principal.
    for inst in instancias:
        sid = inst["sid"]
        agora_attention = bool(inst.get("needs_attention"))
        if agora_attention and not attention_antes.get(sid, False):
            motivo = "erro" if inst.get("attention_reason") == "error" else "aguardando sua ação"
            try:
                icon.notify(f"{inst['titulo']} · {motivo}", "Ação necessária")
            except Exception:
                pass
            if AUDIO_ENABLED:
                _teste_audio()


def monitorar(icon):
    while True:
        checar(icon)
        time.sleep(INTERVALO)


# ---------------------------------------------------------------------------
# Entrada
# ---------------------------------------------------------------------------
def modo_check():
    monitor.coletar()
    instancias, alt, _ = monitor.snapshot()
    if not instancias:
        print("Nenhuma instância ativa de Claude/PI.")
        return 1

    agora = time.time()
    print(f"{len(instancias)} instância(s) ativa(s):\n")
    for inst in sorted(instancias, key=lambda i: i.get("mudou_em", 0), reverse=True):
        idade = formatar_duracao(agora - inst["last_ts"]) if inst["last_ts"] else "?"
        marca = "  <- última alteração" if inst["sid"] == alt else ""
        print(f"  {EMOJI[inst['cor']]} {ESTADO_TEXTO[inst['cor']]:<14} ({idade:>5}) "
              f" {inst['titulo']}{marca}")
        if inst.get("workspace"):
            print(f"        janela: {inst['workspace']}")
        else:
            print("        janela: —")
    print(f"\nSemáforo principal: {EMOJI[monitor.cor_principal()]} "
          f"{ESTADO_TEXTO[monitor.cor_principal()]}")
    print(f"VSCode CLI: {CODE_BIN or 'NÃO ENCONTRADO'}")
    return 0


def main():
    if "--check" in sys.argv:
        sys.exit(modo_check())

    print("Serviço de monitoramento iniciado... ícone criado na bandeja.")
    tray = Icon(
        "ClaudeMonitor",
        ICONES["yellow"],
        title="Monitoramento do Claude",
        menu=construir_menu(),
    )

    def setup(icon):
        icon.visible = True
        threading.Thread(target=monitorar, args=(icon,), daemon=True).start()

    tray.run(setup=setup)


if __name__ == "__main__":
    main()
