"""Weather Service — Fetch current weather and forecasts.

Uses wttr.in (free, no API key) or OpenWeatherMap API.
"""
import logging
import time
from typing import Optional, Dict, Any
from dataclasses import dataclass

logger = logging.getLogger("external.weather")


@dataclass
class WeatherData:
    """Current weather data."""
    location: str = ""
    temperature_c: float = 0.0
    temperature_f: float = 0.0
    condition: str = ""
    humidity: int = 0
    wind_kph: float = 0.0
    feels_like_c: float = 0.0
    visibility_km: float = 0.0
    uv_index: int = 0
    fetched_at: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "location": self.location,
            "temperature_c": self.temperature_c,
            "temperature_f": self.temperature_f,
            "condition": self.condition,
            "humidity": self.humidity,
            "wind_kph": self.wind_kph,
            "feels_like_c": self.feels_like_c,
        }


class WeatherService:
    """Fetch weather data from wttr.in (no API key required)."""

    BASE_URL = "https://wttr.in"

    def __init__(self, api_key: str = ""):
        self._api_key = api_key
        self._cache: Dict[str, WeatherData] = {}
        self._cache_ttl = 600  # 10 minutes
        self._last_fetch = 0.0

    def get_current(self, location: str = "") -> Optional[WeatherData]:
        """Get current weather for a location."""
        if not location:
            location = "auto:ip"

        # Check cache
        cached = self._cache.get(location)
        if cached and (time.time() - self._last_fetch) < self._cache_ttl:
            return cached

        try:
            url = f"{self.BASE_URL}/{location}?format=j1"
            from core.http_pool import fetch
            data = fetch(url, as_json=True)
            if not data:
                return None

            current = data.get("current_condition", [{}])[0]
            weather = WeatherData(
                location=location,
                temperature_c=float(current.get("temp_C", 0)),
                temperature_f=float(current.get("temp_F", 0)),
                condition=current.get("weatherDesc", [{}])[0].get("value", "Unknown"),
                humidity=int(current.get("humidity", 0)),
                wind_kph=float(current.get("windspeedKmph", 0)),
                feels_like_c=float(current.get("FeelsLikeC", 0)),
                visibility_km=float(current.get("visibility", 0)) / 10,
                uv_index=int(current.get("uvIndex", 0)),
                fetched_at=time.time(),
            )

            self._cache[location] = weather
            self._last_fetch = time.time()
            return weather

        except Exception as e:
            logger.warning("Weather fetch failed for %s: %s", location, e)
            return self._cache.get(location)

    def format_weather(self, data: WeatherData) -> str:
        """Format weather data for voice/display."""
        return (
            f"Weather in {data.location}: {data.condition}, "
            f"{data.temperature_c}°C ({data.temperature_f}°F), "
            f"humidity {data.humidity}%, wind {data.wind_kph} km/h"
        )

    def get_stats(self) -> Dict[str, Any]:
        return {
            "cached_locations": len(self._cache),
            "last_fetch": self._last_fetch,
            "cache_ttl": self._cache_ttl,
        }


_weather_instance: Optional[WeatherService] = None


def get_weather_service() -> WeatherService:
    global _weather_instance
    if _weather_instance is None:
        _weather_instance = WeatherService()
    return _weather_instance
