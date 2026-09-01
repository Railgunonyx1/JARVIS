import sys
sys.path.insert(0, r'C:\Users\aayan\Desktop\JARVIS')

# Test importing and using the plugin loader and skill registry
from core.plugin_loader import PluginLoader, list_plugins, get_plugin, jarvis_plugin
from skills import build_default_skill_registry, get_skill, list_all_skills, list_skills

# Plugin loader
pl = PluginLoader()
loaded = pl.discover_and_load()
print(f"Plugins discovered: {list(loaded.keys())}")

# Skill registry
registry = build_default_skill_registry()
print(f"Skills loaded: {len(registry)}")
print(f"Skill names: {sorted(registry.keys())[:10]}...")

# List all skills
all_skills = list_all_skills()
print(f"All skills count: {len(all_skills)}")

# Test get_skill
for name in ['architecture_auditor', 'code_review', 'web_research']:
    cap = get_skill(name)
    if cap:
        print(f"  {name}: {cap.description[:50]}")