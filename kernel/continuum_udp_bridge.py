"""Continuum UDP Bridge v1.2 — Universal Local AI Skills + Guardian Web Connectors + Real Clock Sync.
Works 100% FREE on RTX 3060 (Ollama / llama-server / TabbyAPI / LM Studio) and connects
the Bare-Metal Microkernel to real Internet services (Weather, Web Search, Currency) via Guardian.

Protocol (OIP-UDP v1.2):
  HELLO    (Microkernel -> UDP :8766): "NEWERA-CONTINUUM-HELLO-..."
  HELLO_ACK(Bridge -> Microkernel):    "HELLO_ACK|<engine>|<DD/MM/YYYY>|<seconds_since_midnight>"
  Request  (Microkernel -> UDP :8766): "INTENT|<query>"
  Response (Bridge -> Microkernel):
    - "RESP|<provider>|<title>|<body>"
    - "CMD|<provider>|<skill>|<arg1>|<arg2>"
"""

from __future__ import annotations

import datetime
import importlib.util
import json
import os
import re
import socket
import sys
import threading
import time
import unicodedata
import urllib.request
from pathlib import Path
from typing import Any, Callable

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from kernel.web_connectors import fetch_currency_quote, fetch_live_weather, fetch_web_search

_PII_PATTERNS = [
    ("CPF", re.compile(r"\b\d{3}\.?\d{3}\.?\d{3}-?\d{2}\b")),
    ("EMAIL", re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")),
    ("TELEFONE", re.compile(r"\b(?:\+?55\s?)?(?:\(?\d{2}\)?\s?)(?:9\d{4}|\d{4})-?\d{4}\b")),
]

# Official OS + Internet Compatibility Skills exposed to any local/cloud LLM
NEWERA_OS_SKILLS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "save_memory",
            "description": "Salva uma nota ou lembrete no disco físico do Newera OS (SemanticFS via DMA).",
            "parameters": {
                "type": "object",
                "properties": {
                    "title": {"type": "string", "description": "Título curto da memória"},
                    "content": {"type": "string", "description": "Conteúdo a persistir"},
                },
                "required": ["title", "content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_memory",
            "description": "Busca memórias ou documentos salvos localmente no SemanticFS sem pastas.",
            "parameters": {
                "type": "object",
                "properties": {"query": {"type": "string"}},
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "open_surface",
            "description": "Abre uma janela do Newera OS (semantic, system, guardian ou horizon).",
            "parameters": {
                "type": "object",
                "properties": {
                    "surface": {"type": "string", "enum": ["semantic", "system", "guardian", "horizon"]},
                },
                "required": ["surface"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "network_ping",
            "description": "Executa um teste real de rede (ARP + ICMP Ping) pela placa VirtIO-Net.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "live_weather",
            "description": "Consulta a previsão e temperatura ao vivo na internet para qualquer cidade.",
            "parameters": {
                "type": "object",
                "properties": {"city": {"type": "string", "description": "Nome da cidade"}},
                "required": ["city"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "currency_quote",
            "description": "Consulta a cotação ao vivo na internet de Dólar (USD), Euro (EUR) ou Bitcoin (BTC) em Reais.",
            "parameters": {
                "type": "object",
                "properties": {"currency": {"type": "string", "description": "USD, EUR ou BTC"}},
                "required": ["currency"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "web_search",
            "description": "Pesquisa informações reais na internet (Wikipedia / DuckDuckGo) via Guardian.",
            "parameters": {
                "type": "object",
                "properties": {"query": {"type": "string", "description": "Assunto a pesquisar na web"}},
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "generate_workspace",
            "description": "Gera uma interface visual interativa (KPIs, gráficos de barras e checklist clicável) para planejar viagem, orçamento ou projeto.",
            "parameters": {
                "type": "object",
                "properties": {
                    "title": {"type": "string", "description": "Título do painel"},
                    "budget": {"type": "number", "description": "Orçamento em reais (opcional)"},
                    "days": {"type": "integer", "description": "Número de dias ou etapas"},
                },
                "required": ["title"],
            },
        },
    },
]


_PLUGIN_HANDLERS: dict[str, Callable[[dict[str, Any]], str]] = {}
_PLUGIN_KEYWORDS: list[tuple[str, list[str]]] = []


def discover_skill_plugins() -> int:
    """Auto-discovers community Skill plugins from skills/*.py for the LLM & local router."""
    skills_dir = ROOT / "skills"
    if not skills_dir.exists():
        return 0
    loaded = 0
    for py_file in sorted(skills_dir.glob("*.py")):
        if py_file.name.startswith("_"):
            continue
        try:
            spec = importlib.util.spec_from_file_location(f"newera_skill_{py_file.stem}", py_file)
            if not spec or not spec.loader:
                continue
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            skill_def = getattr(mod, "SKILL_DEF", None)
            runner = getattr(mod, "run", None)
            if isinstance(skill_def, dict) and callable(runner):
                name = skill_def["function"]["name"]
                NEWERA_OS_SKILLS.append(skill_def)
                _PLUGIN_HANDLERS[name] = runner
                kws = list(getattr(mod, "KEYWORDS", []))
                if kws:
                    _PLUGIN_KEYWORDS.append((name, kws))
                loaded += 1
        except Exception as exc:
            print(f"[CONTINUUM-UDP] Failed loading skill plugin {py_file.name}: {exc}", flush=True)
    return loaded


_PLUGINS_LOADED = discover_skill_plugins()


def sanitize_pii(text: str) -> tuple[str, int]:
    count = 0
    redacted = text
    for kind, pat in _PII_PATTERNS:
        def _rep(_m, k=kind):
            nonlocal count
            count += 1
            return f"[GUARDIAN_{k}]"
        redacted = pat.sub(_rep, redacted)
    return redacted, count


def clean_text(text: str, max_len: int = 860) -> str:
    allowed = set("áàâãéêíóôõúçÁÀÂÃÉÊÍÓÔÕÚÇ°•–—\n")
    out = []
    for ch in text:
        if 0x20 <= ord(ch) <= 0x7E or ch in allowed:
            out.append(ch)
        elif ch == "\r":
            continue
        else:
            norm = unicodedata.normalize("NFKD", ch)
            out.append("".join(c for c in norm if 0x20 <= ord(c) <= 0x7E) or " ")
    return "".join(out).replace("|", "/")[:max_len]


def wrap_lines(text: str, width: int = 76) -> str:
    out = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            out.append("")
            continue
        while len(line) > width:
            cut = line.rfind(" ", 0, width)
            if cut <= 20:
                cut = width
            out.append(line[:cut].rstrip())
            line = line[cut:].lstrip()
        out.append(line)
    return "\n".join(out)


def execute_skill(provider: str, skill: str, args: dict[str, Any]) -> str:
    prov = clean_text(provider, 24)
    # Local bare-metal hardware/UI skills -> forwarded as CMD| to microkernel
    if skill == "save_memory":
        title = clean_text(str(args.get("title") or "Nota IA"), 48)
        content = clean_text(str(args.get("content") or title), 220)
        return f"CMD|{prov}|save_memory|{title}|{content}"
    if skill == "search_memory":
        q = clean_text(str(args.get("query") or ""), 48)
        return f"CMD|{prov}|search_memory|{q}|"
    if skill == "open_surface":
        surf = clean_text(str(args.get("surface") or "horizon"), 24)
        return f"CMD|{prov}|open_surface|{surf}|"
    if skill == "network_ping":
        return f"CMD|{prov}|network_ping||"

    # Internet Compatibility Skills (executed safely inside Guardian Web Connector)
    if skill == "live_weather":
        title, body = fetch_live_weather(str(args.get("city") or "São Paulo"))
        return f"RESP|{prov}+web|{clean_text(title, 56)}|{clean_text(wrap_lines(body), 820)}"
    if skill == "currency_quote":
        title, body = fetch_currency_quote(str(args.get("currency") or "USD"))
        m_val = re.search(r"R\$\s*[\d\.,]+", body)
        m_pct = re.search(r"Variação hoje:\s*([-\d\.]+%)", body)
        val_s = m_val.group(0) if m_val else "Ao vivo"
        pct_s = m_pct.group(1) if m_pct else "0%"
        spec = "\n".join([
            f"KPI|Valor Atual|{val_s}|green",
            f"KPI|Variação Hoje|{pct_s}|cyan",
            "KPI|Privacidade|Guardian OK|indigo",
            "TXT|Cotação obtida diretamente da internet sem navegador e sem cookies.",
            "CHK|0|Definir alerta de variação no SemanticFS",
            "CHK|0|Salvar cotação atual no disco VirtIO-Blk",
        ])
        return f"UI|{prov}+web|{clean_text(title, 56)}|{spec}"
    if skill == "generate_workspace":
        title = clean_text(str(args.get("title") or "Planejamento Generativo"), 52)
        budget = float(args.get("budget") or 4000)
        days = int(args.get("days") or 5)
        h = int(budget * 0.36)
        t = int(budget * 0.24)
        a = int(budget * 0.22)
        p = int(budget * 0.18)
        spec = "\n".join([
            f"KPI|Orçamento|R$ {int(budget)}|cyan",
            f"KPI|Horizonte|{days} dias|indigo",
            "KPI|Saldo|Equilibrado|green",
            f"BAR|Hospedagem / Base|R$ {h} (36%)|72|cyan",
            f"BAR|Transporte / Logística|R$ {t} (24%)|48|indigo",
            f"BAR|Alimentação / Operação|R$ {a} (22%)|44|green",
            f"BAR|Experiências + Reserva|R$ {p} (18%)|36|amber",
            "CHK|0|Confirmar reservas principais dentro do teto",
            "CHK|0|Checar previsão do tempo ao vivo via Guardian",
            "CHK|1|Orçamento balanceado automaticamente pelo Newera OS",
        ])
        return f"UI|{prov}|{title}|{spec}"
    if skill == "web_search":
        title, body = fetch_web_search(str(args.get("query") or ""))
        return f"RESP|{prov}+web|{clean_text(title, 56)}|{clean_text(wrap_lines(body), 820)}"

    if skill in _PLUGIN_HANDLERS:
        return _PLUGIN_HANDLERS[skill](args)

    return f"RESP|{prov}|Skill Desconhecida|Skill '{skill}' não reconhecida."


def query_openai_compatible_with_skills(safe_prompt: str) -> str | None:
    base_url = os.getenv("NEWERA_LLM_URL", "").strip()
    provider_hint = os.getenv("NEWERA_LLM_PROVIDER", "").lower()
    api_key = os.getenv("NEWERA_LLM_API_KEY") or os.getenv("OPENAI_API_KEY") or "local-no-key"

    if not base_url:
        if provider_hint == "ollama":
            base_url = "http://localhost:11434/v1"
        elif provider_hint == "llama":
            base_url = "http://localhost:8080/v1"
        elif os.getenv("OPENAI_API_KEY"):
            base_url = "https://api.openai.com/v1"
        else:
            return None

    model = os.getenv("NEWERA_LLM_MODEL") or ("qwen2.5:3b" if "11434" in base_url else "gpt-4o-mini")
    endpoint = f"{base_url.rstrip('/')}/chat/completions"

    payload = json.dumps({
        "model": model,
        "temperature": 0.2,
        "messages": [
            {
                "role": "system",
                "content": (
                    "Você é o núcleo inteligente do Newera OS (bare-metal). "
                    "Use as skills disponíveis sempre que o usuário pedir: clima ao vivo (live_weather), "
                    "cotação de dólar/euro/bitcoin (currency_quote), pesquisa na internet (web_search), "
                    "salvar lembrete no disco (save_memory), buscar memórias locais (search_memory), "
                    "abrir janelas do SO (open_surface) ou testar rede (network_ping). "
                    "Caso contrário, responda em português de forma clara e curta (máx 8 linhas)."
                ),
            },
            {"role": "user", "content": safe_prompt},
        ],
        "tools": NEWERA_OS_SKILLS,
        "tool_choice": "auto",
    }).encode("utf-8")

    req = urllib.request.Request(
        endpoint,
        data=payload,
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"},
    )
    try:
        with urllib.request.urlopen(req, timeout=45) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        msg = data["choices"][0]["message"]
        tool_calls = msg.get("tool_calls") or []
        if tool_calls:
            fn = tool_calls[0]["function"]
            name = fn["name"]
            args = json.loads(fn.get("arguments") or "{}")
            return execute_skill(model, name, args)
        content = (msg.get("content") or "").strip()
        if content:
            return f"RESP|{clean_text(model, 24)}|{clean_text(safe_prompt, 48)}|{clean_text(wrap_lines(content), 820)}"
    except Exception as exc:
        print(f"[CONTINUUM-UDP] LLM call fallback ({endpoint}): {exc}", flush=True)
    return None


def local_skill_router(query: str) -> str:
    q_low = query.lower().strip()

    # Web Skills (real internet even without LLM)
    if any(k in q_low for k in ("tempo em ", "clima em ", "previsao em ", "previsão em ", "temperatura em ")):
        city = re.split(r"\bem\s+", query, maxsplit=1, flags=re.IGNORECASE)[-1].strip(" ?.")
        return execute_skill("web-local", "live_weather", {"city": city})

    if any(k in q_low for k in ("dolar", "dólar", "euro", "bitcoin", "btc", "cotacao", "cotação")):
        cur = "EUR" if "euro" in q_low else "BTC" if ("bitcoin" in q_low or "btc" in q_low) else "USD"
        return execute_skill("web-local", "currency_quote", {"currency": cur})

    for prefix in ("pesquise ", "pesquisar ", "web ", "wikipedia "):
        if q_low.startswith(prefix):
            return execute_skill("web-local", "web_search", {"query": query[len(prefix) :].strip()})

    for prefix in ("lembre ", "lembrar ", "anote ", "anotar ", "guarde ", "guardar ", "salve ", "salvar "):
        if q_low.startswith(prefix):
            body = query[len(prefix) :].strip()
            body = re.sub(r"^(?:que|de|na memoria|na memória)\s+", "", body, flags=re.IGNORECASE).strip()
            return execute_skill("skill-local", "save_memory", {"title": body[:36] or "Lembrete", "content": body})

    if "ping" in q_low or "testar rede" in q_low:
        return execute_skill("skill-local", "network_ping", {})

    if any(k in q_low for k in ("abra ", "abrir ", "mostrar ", "mostre ")):
        if any(k in q_low for k in ("sistema", "hardware", "rede", "pci")):
            return execute_skill("skill-local", "open_surface", {"surface": "system"})
        if any(k in q_low for k in ("guardian", "seguranca", "segurança", "caps")):
            return execute_skill("skill-local", "open_surface", {"surface": "guardian"})
        if any(k in q_low for k in ("memoria", "memória", "notas")):
            return execute_skill("skill-local", "open_surface", {"surface": "semantic"})

    # Check auto-discovered community skill plugins in skills/*.py
    for plugin_name, kws in _PLUGIN_KEYWORDS:
        if any(kw in q_low for kw in kws):
            if plugin_name == "calculate_expression":
                expr = re.sub(r"^(?:calcule|calcular|quanto\s+[eé])\s+", "", query, flags=re.IGNORECASE).strip(" ?")
                return execute_skill("plugin", plugin_name, {"expression": expr})
            if plugin_name == "play_youtube_music":
                song = re.sub(r"^(?:toque|tocar|coloque\s+m[uú]sica|youtube|ouvir)\s+", "", query, flags=re.IGNORECASE).strip(" ?")
                return execute_skill("plugin", plugin_name, {"query": song or query})
            if plugin_name == "stop_music":
                return execute_skill("plugin", plugin_name, {})
            return execute_skill("plugin", plugin_name, {"goal": query})

    if any(k in q_low for k in ("viagem", "orcamento", "orçamento", "planejar", "plano", "projeto")):
        m_num = re.search(r"(\d[\d\.]{2,})", query)
        budget = float(m_num.group(1).replace(".", "")) if m_num else 4000.0
        m_days = re.search(r"(\d+)\s*dias?", q_low)
        days = int(m_days.group(1)) if m_days else 5
        return execute_skill("gen-ui", "generate_workspace", {"title": query[:48], "budget": budget, "days": days})

    for prefix in ("busque ", "buscar ", "procure "):
        if q_low.startswith(prefix):
            return execute_skill("skill-local", "search_memory", {"query": query[len(prefix) :].strip()})

    return execute_skill("web-local", "web_search", {"query": query})


def process_intent(query: str) -> str:
    safe_query, pii_count = sanitize_pii(query)
    res = query_openai_compatible_with_skills(safe_query) or local_skill_router(safe_query)
    if pii_count > 0 and res.startswith("RESP|"):
        res += f"\n\n[Guardian] {pii_count} dado(s) sensível(is) protegido(s)."
    return res


def _clock_sync_payload(engine: str) -> str:
    now = datetime.datetime.now()
    date_str = now.strftime("%d/%m/%Y")
    secs_today = now.hour * 3600 + now.minute * 60 + now.second
    return f"HELLO_ACK|{engine}|{date_str}|{secs_today}"


IPC_DIR = ROOT / "data" / "ipc"
IPC_DIR.mkdir(parents=True, exist_ok=True)
AUDIO_STATE_FILE = IPC_DIR / "audio_state.txt"
VOICE_CMD_FILE = IPC_DIR / "voice_cmd.txt"
SPOKEN_INTENT_FILE = IPC_DIR / "spoken_intent.txt"


def notify_voice_tts(reply: str) -> None:
    """Sends a concise spoken summary to the Windows Neural Voice Daemon via firewall-free IPC."""
    if reply.startswith("UI|plugin:youtube|") or reply.startswith("RESP|plugin:youtube|"):
        return
    spoken = ""
    if reply.startswith("RESP|"):
        parts = reply.split("|", 3)
        spoken = parts[3] if len(parts) >= 4 else ""
    elif reply.startswith("UI|"):
        parts = reply.split("|", 3)
        title = parts[2] if len(parts) >= 3 else "Painel pronto"
        kpis = [
            f"{ln.split('|')[1]} {ln.split('|')[2]}"
            for ln in (parts[3].splitlines() if len(parts) >= 4 else [])
            if ln.startswith("KPI|") and len(ln.split("|")) >= 3
        ]
        spoken = f"{title}. " + ", ".join(kpis[:3]) if kpis else title
    elif reply.startswith("CMD|"):
        parts = reply.split("|", 4)
        skill = parts[2] if len(parts) >= 3 else ""
        arg1 = parts[3] if len(parts) >= 4 else ""
        if skill == "save_memory":
            spoken = f"Salvei na sua memória: {arg1}."
        elif skill == "open_surface":
            spoken = f"Abrindo {arg1}."
        elif skill == "network_ping":
            spoken = "Executando teste de rede no microkernel."
        elif skill == "search_memory":
            spoken = f"Buscando por {arg1} na sua memória semântica."

    if spoken:
        try:
            VOICE_CMD_FILE.write_text(f"SPEAK|{spoken[:320]}", encoding="utf-8")
        except Exception:
            pass


def serve_forever(port: int = 8766) -> None:
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind(("0.0.0.0", port))
    active = os.getenv("NEWERA_LLM_MODEL") or os.getenv("NEWERA_LLM_PROVIDER") or "skills-web"
    print(f"[CONTINUUM-UDP] Listening on 0.0.0.0:{port} (engine={active}, skills={len(NEWERA_OS_SKILLS)})", flush=True)
    state: dict[str, Any] = {"microkernel_addr": None}

    def _ipc_relay_worker() -> None:
        """Relays live VU meter (data/ipc/audio_state.txt) & transcribed speech to Bare-Metal via local UDP."""
        while True:
            mk = state["microkernel_addr"]
            if mk is not None:
                try:
                    if AUDIO_STATE_FILE.exists():
                        audio_pkt = AUDIO_STATE_FILE.read_text(encoding="utf-8", errors="replace").strip()
                        if audio_pkt.startswith("AUDIO|"):
                            sock.sendto(audio_pkt.encode("utf-8"), mk)
                except Exception:
                    pass
                try:
                    if SPOKEN_INTENT_FILE.exists():
                        spoken_q = SPOKEN_INTENT_FILE.read_text(encoding="utf-8", errors="replace").strip()
                        SPOKEN_INTENT_FILE.unlink(missing_ok=True)
                        if spoken_q:
                            print(f"[CONTINUUM-UDP] SPOKEN INTENT: {spoken_q}", flush=True)
                            reply = process_intent(spoken_q)
                            # Voice-first UX: spoken Q&A (RESP|) responds purely by voice over the Jarvis Orb
                            # without popping up a text window! Only visual UI| or OS Skill CMD| opens a window.
                            if reply.startswith("CMD|") or reply.startswith("UI|"):
                                sock.sendto(reply.encode("utf-8")[:1360], mk)
                            notify_voice_tts(reply)
                except Exception:
                    pass
            time.sleep(0.08)

    threading.Thread(target=_ipc_relay_worker, daemon=True).start()

    while True:
        data, addr = sock.recvfrom(2048)
        msg = data.decode("utf-8", errors="replace").strip()

        if msg.startswith("AUDIO|"):
            if state["microkernel_addr"] is not None:
                sock.sendto(msg.encode("utf-8"), state["microkernel_addr"])
            continue

        print(f"[CONTINUUM-UDP] RX from {addr}: {msg}", flush=True)

        if msg.startswith("NEWERA-CONTINUUM-HELLO"):
            state["microkernel_addr"] = addr
            ack = _clock_sync_payload(active)
            sock.sendto(ack.encode("utf-8"), addr)
        elif msg.startswith("MIC_TRIGGER|"):
            state["microkernel_addr"] = addr
            try:
                VOICE_CMD_FILE.write_text("MIC_START|", encoding="utf-8")
            except Exception:
                pass
        elif msg.startswith("INTENT|"):
            state["microkernel_addr"] = addr
            q = msg[len("INTENT|") :].strip()
            reply = process_intent(q)
            sock.sendto(reply.encode("utf-8")[:1360], addr)
            notify_voice_tts(reply)
            print(f"[CONTINUUM-UDP] TX to {addr}: {reply[:90]}", flush=True)


if __name__ == "__main__":
    serve_forever(int(os.getenv("NEWERA_UDP_PORT", "8766")))
