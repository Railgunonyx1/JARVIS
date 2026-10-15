"""Weather — key-free forecasts via open-meteo (the wttr.in lineage).

Derived from the chubin/wttr.in philosophy: an assistant should answer
"do I need a jacket?" with zero API keys, zero sign-up, zero tracking. The
open-meteo service provides geocoding and forecasts free of charge; this
module wraps it through the shared pooled HTTP client with a WMO weather-code
translation table so replies read like weather, not sensor dumps.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from tools.schema import ToolResult

logger = logging.getLogger(__name__)

_GEOCODE_URL = "https://geocoding-api.open-meteo.com/v1/search?name={name}&count=1&language=en&format=json"
_FORECAST_URL = (
    "https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}"
    "&current=temperature_2m,apparent_temperature,relative_humidity_2m,weather_code,wind_speed_10m"
    "&daily=temperature_2m_max,temperature_2m_min,precipitation_probability_max,weather_code"
    "&timezone=auto&forecast_days={days}"
)

# WMO weather interpretation codes (0-99) → plain language.
_WMO = {
    0: "Clear sky", 1: "Mainly clear", 2: "Partly cloudy", 3: "Overcast",
    45: "Fog", 48: "Depositing rime fog",
    51: "Light drizzle", 53: "Moderate drizzle", 55: "Dense drizzle",
    56: "Light freezing drizzle", 57: "Dense freezing drizzle",
    61: "Slight rain", 63: "Moderate rain", 65: "Heavy rain",
    66: "Light freezing rain", 67: "Heavy freezing rain",
    71: "Slight snowfall", 73: "Moderate snowfall", 75: "Heavy snowfall",
    77: "Snow grains",
    80: "Slight rain showers", 81: "Moderate rain showers", 82: "Violent rain showers",
    85: "Slight snow showers", 86: "Heavy snow showers",
    95: "Thunderstorm", 96: "Thunderstorm with slight hail", 99: "Thunderstorm with heavy hail",
}


def _wmo_text(code: Any) -> str:
    try:
        return _WMO.get(int(code), f"weather code {code}")
    except (TypeError, ValueError):
        return "unknown"


def _fetch_json(url: str, timeout: float) -> dict[str, Any] | None:
    try:
        from core.http_pool import fetch
    except Exception:
        return None
    try:
        raw = fetch(url, timeout=timeout)
        if not raw:
            return None
        return json.loads(str(raw))
    except Exception as exc:
        logger.debug("weather: fetch/parse failed for %s: %s", url, exc)
        return None


def _geocode(location: str, timeout: float) -> dict[str, Any] | None:
    data = _fetch_json(_GEOCODE_URL.format(name=re.sub(r"\s+", "%20", location)), timeout)
    if not data or not data.get("results"):
        return None
    return data["results"][0]


def _current_line(cur: dict[str, Any]) -> str:
    return (
        f"{cur.get('temperature_2m', '?')}°C (feels {cur.get('apparent_temperature', '?')}°C), "
        f"{_wmo_text(cur.get('weather_code'))}, "
        f"humidity {cur.get('relative_humidity_2m', '?')}%, "
        f"wind {cur.get('wind_speed_10m', '?')} km/h"
    )


def weather_get(args: dict[str, Any]) -> ToolResult:
    """Current conditions + short forecast for a location — no API key."""
    location = str(args.get("location") or "").strip()
    lat = args.get("lat")
    lon = args.get("lon")
    try:
        days = min(int(args.get("days") or 3), 7)
    except (TypeError, ValueError):
        return ToolResult(success=False, error="days must be an integer")

    if lat is not None and lon is not None:
        place = str(args.get("label") or f"{lat},{lon}")
    else:
        if not location:
            return ToolResult(success=False, error="location is required — a place name, or lat/lon")
        geo = _geocode(location, timeout=10)
        if not geo:
            return ToolResult(success=False, error=f"could not geocode location: {location}")
        place = f"{geo.get('name', location)}" + (
            f", {geo.get('country')}" if geo.get("country") else ""
        )
        lat, lon = geo.get("latitude"), geo.get("longitude")
        if lat is None or lon is None:
            return ToolResult(success=False, error=f"geocoding returned no coordinates for: {location}")

    data = _fetch_json(_FORECAST_URL.format(lat=lat, lon=lon, days=days), timeout=15)
    if not data:
        return ToolResult(success=False, error="weather service unreachable or returned nothing")

    lines = [f"Weather — {place}:"]
    cur = data.get("current") or {}
    if cur:
        lines.append(f"  now: {_current_line(cur)}")
    daily = data.get("daily") or {}
    dates = daily.get("time") or []
    for i, day in enumerate(dates[:days]):
        try:
            code = (daily.get("weather_code") or [None] * len(dates))[i]
            tmax = (daily.get("temperature_2m_max") or [None] * len(dates))[i]
            tmin = (daily.get("temperature_2m_min") or [None] * len(dates))[i]
            pop = (daily.get("precipitation_probability_max") or [None] * len(dates))[i]
            rain = f", rain {pop}%" if pop is not None else ""
            lines.append(f"  {day}: {_wmo_text(code)}, {tmin}–{tmax}°C{rain}")
        except (IndexError, TypeError):
            continue
    if len(lines) == 1:
        return ToolResult(success=False, error="weather service returned no usable data")
    return ToolResult(success=True, output="\n".join(lines))


__all__ = ["weather_get"]
