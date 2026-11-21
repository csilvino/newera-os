"""Geospatial & Live Weather Capability Engine (Open-Meteo + OSM with offline fallback)."""

from __future__ import annotations

from typing import Any

import httpx

from ...models import CapabilityManifest, CapabilityPermission, WorkspaceBlock
from ..base import CapabilityContext, CapabilityEngine

_KNOWN_CITIES: dict[str, tuple[str, float, float]] = {
    "florianopolis": ("Florianópolis, SC", -27.5954, -48.5480),
    "rio de janeiro": ("Rio de Janeiro, RJ", -22.9068, -43.1729),
    "sao paulo": ("São Paulo, SP", -23.5505, -46.6333),
    "gramado": ("Gramado, RS", -29.3746, -50.8764),
    "salvador": ("Salvador, BA", -12.9714, -38.5014),
    "recife": ("Recife, PE", -8.0476, -34.8770),
    "curitiba": ("Curitiba, PR", -25.4284, -49.2733),
    "fortaleza": ("Fortaleza, CE", -3.7319, -38.5267),
    "belo horizonte": ("Belo Horizonte, MG", -19.9167, -43.9345),
    "lisboa": ("Lisboa, Portugal", 38.7223, -9.1393),
    "paris": ("Paris, França", 48.8566, 2.3522),
    "toquio": ("Tóquio, Japão", 35.6762, 139.6503),
    "nova york": ("Nova York, EUA", 40.7128, -74.0060),
    "buenos aires": ("Buenos Aires, Argentina", -34.6037, -58.3816),
}

_WMO_CODES: dict[int, str] = {
    0: "Céu limpo",
    1: "Predominantemente limpo",
    2: "Parcialmente nublado",
    3: "Nublado",
    45: "Neblina",
    51: "Garoa leve",
    61: "Chuva leve",
    63: "Chuva moderada",
    80: "Pancadas de chuva",
    95: "Trovoada",
}


def _normalize_city(name: str) -> str:
    import unicodedata
    nfkd = unicodedata.normalize("NFKD", name.lower().strip())
    return "".join(ch for ch in nfkd if not unicodedata.combining(ch))


class GeoWeatherEngine(CapabilityEngine):
    manifest = CapabilityManifest(
        id="geo_weather_engine",
        name="Motor Geoespacial & Clima",
        version="0.1.0",
        description="Mapas interativos e previsão do tempo real via Open-Meteo com fallback offline.",
        intents=["travel_planning", "weather_check"],
        keywords=["mapa", "viagem", "clima", "tempo", "previsão", "previsao", "destino", "cidade"],
        permissions=CapabilityPermission(network=True, vault="none", semantic_fs="none"),
        source="builtin",
    )

    async def _resolve_city(self, destination: str) -> tuple[str, float, float]:
        norm = _normalize_city(destination)
        for key, coords in _KNOWN_CITIES.items():
            if key in norm or norm in key:
                return coords

        # Try Open-Meteo Geocoding API (no API key required)
        try:
            async with httpx.AsyncClient(timeout=2.5) as client:
                resp = await client.get(
                    "https://geocoding-api.open-meteo.com/v1/search",
                    params={"name": destination, "count": 1, "language": "pt", "format": "json"},
                )
                data = resp.json()
                if data.get("results"):
                    first = data["results"][0]
                    label = f"{first['name']}, {first.get('country', '')}".strip(", ")
                    return label, float(first["latitude"]), float(first["longitude"])
        except Exception:
            pass

        return ("Florianópolis, SC", -27.5954, -48.5480)

    async def _fetch_weather(self, lat: float, lon: float, days: int) -> tuple[list[dict[str, Any]], bool]:
        try:
            async with httpx.AsyncClient(timeout=2.8) as client:
                resp = await client.get(
                    "https://api.open-meteo.com/v1/forecast",
                    params={
                        "latitude": lat,
                        "longitude": lon,
                        "daily": "weathercode,temperature_2m_max,temperature_2m_min,precipitation_probability_max",
                        "timezone": "auto",
                        "forecast_days": max(1, min(days, 7)),
                    },
                )
                daily = resp.json().get("daily", {})
                dates = daily.get("time", [])
                codes = daily.get("weathercode", [])
                tmax = daily.get("temperature_2m_max", [])
                tmin = daily.get("temperature_2m_min", [])
                rain = daily.get("precipitation_probability_max", [])
                forecast = []
                for i in range(len(dates)):
                    code = int(codes[i]) if i < len(codes) else 1
                    forecast.append(
                        {
                            "date": dates[i],
                            "condition": _WMO_CODES.get(code, "Tempo estável"),
                            "temp_max": round(float(tmax[i]), 1) if i < len(tmax) else 26.0,
                            "temp_min": round(float(tmin[i]), 1) if i < len(tmin) else 19.0,
                            "rain_prob": int(rain[i]) if i < len(rain) and rain[i] is not None else 15,
                        }
                    )
                if forecast:
                    return forecast, True
        except Exception:
            pass

        # Deterministic offline fallback
        fallback = [
            {
                "date": f"Dia {i + 1}",
                "condition": "Parcialmente nublado" if i % 2 else "Céu limpo",
                "temp_max": 26 + (i % 3),
                "temp_min": 18 + (i % 2),
                "rain_prob": 20 if i % 2 else 10,
            }
            for i in range(max(1, min(days, 7)))
        ]
        return fallback, False

    async def execute(self, ctx: CapabilityContext) -> list[WorkspaceBlock]:
        destination = str(ctx.params.get("destination", "Florianópolis"))
        days = int(ctx.params.get("days", 5))
        label, lat, lon = await self._resolve_city(destination)
        forecast, is_live = await self._fetch_weather(lat, lon, days)

        markers = [
            {"name": f"Centro — {label}", "lat": lat, "lon": lon, "kind": "base"},
            {"name": "Ponto Turístico Principal", "lat": round(lat + 0.025, 4), "lon": round(lon + 0.032, 4), "kind": "poi"},
            {"name": "Zona Gastronômica", "lat": round(lat - 0.018, 4), "lon": round(lon + 0.019, 4), "kind": "food"},
        ]

        return [
            WorkspaceBlock(
                id="blk_map_weather",
                type="map_weather",
                title=f"Mapa & Clima — {label}",
                capability=self.manifest.id,
                col_span=5,
                data={
                    "destination": label,
                    "lat": lat,
                    "lon": lon,
                    "markers": markers,
                    "forecast": forecast,
                    "live_weather": is_live,
                },
            )
        ]
