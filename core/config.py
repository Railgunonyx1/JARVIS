class ModelCatalog:
    """Centralized model name catalog — single source of truth for all LLM model references."""
    
    # Gemini models (primary providers)
    GEMINI_FLASH_LITE = "gemini-2.5-flash-lite"
    GEMINI_FLASH = "gemini-2.5-flash"
    GEMINI_FLASH_20 = "gemini-2.0-flash"
    GEMINI_1_5_FLASH = "gemini-1.5-flash"
    
    # Provider-specific models
    GROQ_LLAMA3_1 = "llama-3.1-8b-instant"
    GROQ_MIXTRAL = "mixtral-8x7b-instant"
    
    # OpenRouter models
    OPENROUTER_GEMINI = "google/gemini-2.5-flash"
    OPENROUTER_CLAUDE = "anthropic/claude-3.5-sonnet"
    OPENROUTER_MIXTRAL = "mistralai/mixtral-8x7b-instant"
    
    # Default mappings by tier
    DEFAULT_BY_TIER = {
        "tiny": GROQ_LLAMA3_1,
        "small": GROQ_LLAMA3_1,
        "medium": OPENROUTER_GEMINI,
        "large": GEMINI_FLASH_LITE,
    }
    
    @classmethod
    def get_model(cls, tier: str, provider: str | None = None) -> str:
        """Get model name by tier and optional provider."""
        if provider and provider in cls.__dict__:
            # Check if it's a direct model constant
            val = getattr(cls, provider, None)
            if val:
                return val
        return cls.DEFAULT_BY_TIER.get(tier, cls.GEMINI_FLASH_LITE)
    
    @classmethod
    def get_model_for_purpose(cls, purpose: str) -> str:
        """Get model by intended use case."""
        purposes = {
            "planning": cls.GEMINI_FLASH_LITE,
            "execution": cls.GEMINI_FLASH,
            "streaming": cls.GEMINI_FLASH,
            "coding": cls.OPENROUTER_MIXTRAL,
            "analysis": cls.GEMINI_FLASH,
            "creative": cls.OPENROUTER_CLAUDE,
        }
        return purposes.get(purpose, cls.GEMINI_FLASH_LITE)


# Failure recovery configuration
FAILURE_RECOVERY_CONFIG = {
    "tool.executed": "retry",
    "action.executed": "retry",
    "llm.completed": "replan",
    "permission.checked": "abort",
    "llm.failed": "replan",
}


class Config:
    """Centralized configuration class."""
    
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._data = {}
            # Load default failure_analyzer config
            cls._instance._data["failure_analyzer"] = {
                "tool.executed": "retry",
                "action.executed": "retry",
                "llm.completed": "replan",
                "permission.checked": "abort",
                "llm.failed": "replan",
            }
            # Try to load TOML config
            cls._instance._load_toml_config()
        return cls._instance
    
    def _load_toml_config(self) -> None:
        """Load failure analyzer config from TOML file if available."""
        import os
        project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        toml_path = os.path.join(project_root, "config", "failure_analyzer.toml")
        if os.path.exists(toml_path):
            try:
                import tomllib
                with open(toml_path, "rb") as f:
                    toml_data = tomllib.load(f)
                    if "failure_analyzer" in toml_data:
                        self._data["failure_analyzer"].update(toml_data["failure_analyzer"])
            except Exception:
                pass  # Silently fall back to defaults
    
    def get(self, section: str, key: str, default=None):
        """Get a config value."""
        return self._data.get(section, {}).get(key, default)
    
    def get_section(self, section: str) -> dict:
        """Get all values in a config section."""
        return self._data.get(section, {})
    
    def set(self, section: str, key: str, value) -> None:
        """Set a config value."""
        if section not in self._data:
            self._data[section] = {}
        self._data[section][key] = value
    
    def get_failure_recovery(self, event_name: str, default: str = "replan") -> str:
        """Get recovery action for a failure event, with config override."""
        # Check for config override first
        config_val = self.get("failure_analyzer", event_name, default)
        if config_val and config_val != default:
            return config_val
        # Fall back to default mapping
        return FAILURE_RECOVERY_CONFIG.get(event_name, default)