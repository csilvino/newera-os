"""Guardian-Mediated Web Compatibility Connectors (Zero API Keys, Zero Trackers).
Connects the Newera OS Bare-Metal Microkernel to real live Internet data:
  1. live_weather(city)    -> Open-Meteo Geocoding + Live Weather
  2. currency_quote(code)  -> AwesomeAPI Live Exchange Rates (USD, EUR, BTC -> BRL)
  3. web_search(query)     -> Wikipedia PT-BR + DuckDuckGo Instant Answer
"""

from __future__ import annotations

import json
import urllib.parse
import urllib.request

_HEADERS = {"User-Agent": "NeweraOS/0.9 (Intent-Based OS; Guardian Proxy)"}

_WMO_PT = {
    0: "Céu limpo",
    1: "Predominantemente limpo",
    2: "Parcialmente nublado",
    3: "Nublado",
    45: "Neblina",
    51: "Garoa leve",
    61: "Chuva leve",
    63: "Chuva moderada",
    65: "Chuva forte",
    80: "Pancadas de chuva",
    95: "Tempestade com trovoadas",
}


def _http_get_json(url: str, timeout: float = 5.0) -> dict | list | None:
    req = urllib.request.Request(url, headers=_HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8", errors="replace"))
    except Exception:
        return None


def fetch_live_weather(city: str) -> tuple[str, str]:
    q = urllib.parse.quote(city.strip() or "São Paulo")
    geo = _http_get_json(
        f"https://geocoding-api.open-meteo.com/v1/search?name={q}&count=1&language=pt&format=json"
    )
    if not isinstance(geo, dict) or not geo.get("results"):
        return (f"Clima — {city}", f"Não foi possível localizar '{city}' na API Open-Meteo.")

    loc = geo["results"][0]
    name = loc.get("name", city)
    country = loc.get("country", "")
    lat, lon = loc["latitude"], loc["longitude"]

    weather = _http_get_json(
        f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}"
        "&current=temperature_2m,relative_humidity_2m,wind_speed_10m,weather_code"
        "&daily=temperature_2m_max,temperature_2m_min&timezone=auto&forecast_days=1"
    )
    if not isinstance(weather, dict) or "current" not in weather:
        return (f"Clima — {name}", "Serviço meteorológico temporariamente indisponível.")

    cur = weather["current"]
    daily = weather.get("daily", {})
    cond = _WMO_PT.get(int(cur.get("weather_code", 0)), "Tempo estável")
    temp = cur.get("temperature_2m")
    hum = cur.get("relative_humidity_2m")
    wind = cur.get("wind_speed_10m")
    tmax = (daily.get("temperature_2m_max") or [temp])[0]
    tmin = (daily.get("temperature_2m_min") or [temp])[0]

    body = (
        f"Dados ao vivo via Guardian Web Connector (Open-Meteo):\n\n"
        f"• Local: {name}, {country}\n"
        f"• Condição agora: {cond}\n"
        f"• Temperatura atual: {temp}°C (Mín {tmin}°C / Máx {tmax}°C)\n"
        f"• Umidade: {hum}%  •  Vento: {wind} km/h\n\n"
        f"Zero rastreadores enviados — consulta anônima mediada pelo Guardian."
    )
    return (f"Clima ao Vivo — {name}", body)


def fetch_currency_quote(currency: str = "USD") -> tuple[str, str]:
    code = currency.upper().strip()
    if "EURO" in code or "EUR" in code:
        pair, key, label = "EUR-BRL", "EURBRL", "Euro (EUR)"
    elif "BITCOIN" in code or "BTC" in code:
        pair, key, label = "BTC-BRL", "BTCBRL", "Bitcoin (BTC)"
    else:
        pair, key, label = "USD-BRL", "USDBRL", "Dólar Americano (USD)"

    data = _http_get_json(f"https://economia.awesomeapi.com.br/json/last/{pair}")
    if not isinstance(data, dict) or key not in data:
        return (f"Cotação — {label}", "Não foi possível obter a cotação ao vivo agora.")

    item = data[key]
    bid = float(item.get("bid", 0))
    high = float(item.get("high", 0))
    low = float(item.get("low", 0))
    pct = item.get("pctChange", "0")
    ts = item.get("create_date", "")

    body = (
        f"Cotação financeira ao vivo (Guardian Web Connector):\n\n"
        f"• Ativo: {label} -> Real Brasileiro (BRL)\n"
        f"• Valor atual: R$ {bid:,.2f}\n"
        f"• Variação hoje: {pct}%  (Mín R$ {low:,.2f} / Máx R$ {high:,.2f})\n"
        f"• Atualizado em: {ts}\n\n"
        f"Conexão direta sem navegador e sem cookies."
    )
    return (f"Cotação ao Vivo — {label}", body)


def fetch_web_search(query: str) -> tuple[str, str]:
    q_clean = query.strip()
    if not q_clean:
        return ("Busca Web", "Informe um termo para pesquisar.")

    # 1. Try Wikipedia PT-BR Search + Summary (fast, clean, Portuguese)
    enc = urllib.parse.quote(q_clean)
    search_res = _http_get_json(
        f"https://pt.wikipedia.org/w/api.php?action=opensearch&search={enc}&limit=1&namespace=0&format=json"
    )
    if isinstance(search_res, list) and len(search_res) >= 2 and search_res[1]:
        page_title = search_res[1][0]
        summary_data = _http_get_json(
            f"https://pt.wikipedia.org/api/rest_v1/page/summary/{urllib.parse.quote(page_title)}"
        )
        if isinstance(summary_data, dict) and summary_data.get("extract"):
            extract = summary_data["extract"][:520]
            body = (
                f"Fonte: Wikipedia PT-BR (via Guardian Web Connector)\n\n"
                f"{extract}\n\n"
                f"Zero rastreadores • Consulta filtrada pelo Guardian Sandbox."
            )
            return (f"Web — {page_title}", body)

    # 2. Fallback: DuckDuckGo Instant Answer API
    ddg = _http_get_json(
        f"https://api.duckduckgo.com/?q={enc}&format=json&no_html=1&skip_disambig=1"
    )
    if isinstance(ddg, dict):
        abstract = ddg.get("AbstractText") or ""
        if abstract:
            return (
                f"Web — {q_clean[:40]}",
                f"Fonte: DuckDuckGo (via Guardian Web Connector)\n\n{abstract[:520]}",
            )

    return (
        f"Busca Web — {q_clean[:36]}",
        f"Nenhum resumo direto encontrado para '{q_clean}'. Tente termos mais específicos.",
    )
