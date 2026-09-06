"""Set the model preference for JARVIS MK-X.

Usage:
    python scripts/set_pref.py [speed|single|<model>]
        speed   - enable three-tier cascade routing (default, fastest)
        single  - disable cascade, use single-model auto-routing
        <model> - lock routing to a specific model name
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

from providers.model_registry import ModelRegistry  # noqa: E402

registry = ModelRegistry.instance()

arg = sys.argv[1] if len(sys.argv) > 1 else "speed"

if arg == "speed":
    result = registry.set_cascade(True)
elif arg == "single":
    result = registry.set_cascade(False)
else:
    result = registry.set_model(arg)

status = registry.get_status()
print(f"Model preference set: {result}")
print(
    f"  Active: {status['active_model'] or 'auto'}  "
    f"Auto: {status['auto_mode']}  Cascade: {status['cascade_mode']}"
)
