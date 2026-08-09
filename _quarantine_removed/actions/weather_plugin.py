"""Example Weather Plugin for JARVIS MK-X."""

from core.plugin_loader import jarvis_plugin

@jarvis_plugin(
    name="plugin.weather",
    description="Fetch weather information for a city",
    patterns=[r"\b(weather in|forecast for)\s+(.+)"]
)
def get_weather(city: str = "London") -> str:
    """Fetch current weather report."""
    return f"The current weather report for {city.title()} is 22°C and clear skies, sir."
