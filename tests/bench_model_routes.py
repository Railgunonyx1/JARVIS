#!/usr/bin/env python3
"""Model routing benchmark - basic tests for provider routing."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

def test_router_initialization():
    """Test that router can be initialized."""
    try:
        from providers.router import ProviderRouter
        from core.api_keys import router_api_keys
        import tomllib
        
        config_path = Path("config/models.toml")
        if config_path.exists():
            with open(config_path, 'rb') as f:
                models_config = tomllib.load(f)
            router = ProviderRouter(models_config, router_api_keys())
            print("✓ Router initialized successfully")
            print(f"  Providers configured: {len(getattr(router, 'providers', {}))}")
        else:
            print("⚠ models.toml not found")
    except Exception as e:
        print(f"✗ Router test failed: {e}")

if __name__ == "__main__":
    print("Running model routing benchmarks...")
    print("=" * 50)
    test_router_initialization()
    print("=" * 50)
    print("\nModel routing benchmarks completed!")
