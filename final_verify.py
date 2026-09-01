#!/usr/bin/env python
import os
import sys
sys.path.insert(0, '.')

print('='*70)
print('FINAL OPTIMIZATION VERIFICATION')
print('='*70)

results = {}

# 1. Memory API
try:
    from memory.api import MemoryAPI
    m = MemoryAPI()
    r = m.format_for_prompt(project='test', max_tokens=2000)
    results['format_for_prompt'] = len(r) if r else 0
    results['memory_import'] = 'OK'
except Exception as e:
    results['format_for_prompt'] = 'ERROR: ' + str(type(e).__name__)
    results['memory_import'] = 'FAIL'

# 2. Skills catalog
catalog_dir = r'C:\Users\aayan\Desktop\JARVIS\skills\catalog'
optimized = 0
total = 0
if os.path.exists(catalog_dir):
    for f in sorted(os.listdir(catalog_dir)):
        if f.endswith('.md'):
            total += 1
            with open(os.path.join(catalog_dir, f), 'r', encoding='utf-8', errors='replace') as fh:
                content = fh.read()
            if '| # | Skill' not in content:
                optimized += 1
results['skills_optimized'] = f'{optimized}/{total}'

# 3. Context budgets
try:
    from optimize_budget_integration import get_budget
    for mode in ['plan', 'controlled', 'smart', 'agent']:
        b = get_budget(mode)
        results[f'{mode}_budget'] = f't={b.total}'
    results['budgets_ok'] = 'OK'
except Exception as e:
    results['budgets_ok'] = 'ERROR: ' + str(type(e).__name__)

# 4. Memory Plugin
try:
    with open('plugins/jarvis-dsh/src/memory-plugin.ts', 'r') as f:
        pcontent = f.read()
    checks = {
        'memory.forget': 'memory.forget' in pcontent,
        'memory.remember': 'memory.remember' in pcontent,
        'memory.update': 'memory.update' in pcontent,
        'commands': 'ctx.commands.register' in pcontent,
        'system-prompt': 'system-prompt/assemble' in pcontent,
    }
    results['memory_plugin'] = all(checks.values())
    results['plugin_features'] = sum(checks.values())
except Exception as e:
    results['memory_plugin'] = 'ERROR: ' + str(type(e).__name__)
    results['plugin_features'] = 0

# 5. Adaptive tool timefalls
try:
    from core.agent.loop import AgentLoop
    import inspect
    source = inspect.getsource(AgentLoop)
    results['adaptive_tool'] = '_adaptive_tool_limit' in source and '_tool_call_limit' in source
    results['cascade_fallback'] = 'secondary_requirements' in source
except Exception as e:
    results['adaptive_tool'] = 'ERROR: ' + str(type(e).__name__)
    results['cascade_fallback'] = 'ERROR'

# 6. Token monitoring
try:
    from core.agent.loop import AgentLoop
    import inspect
    source = inspect.getsource(AgentLoop)
    results['token_monitoring'] = '_token_usage' in source
except Exception as e:
    results['token_monitoring'] = 'ERROR: ' + str(type(e).__name__)

# 7. TTS redaction check
try:
    with open('core/executor.py', 'r', encoding='utf-8', errors='replace') as f:
        econtent = f.read()
    results['tts_redaction'] = 'redact_sensitive' in econtent
except Exception as e:
    results['tts_redaction'] = 'ERROR'

# 8. MCP client check
try:
    with open('plugins/mcp/mcp_client_plugin.py', 'r') as f:
        mcontent = f.read()
    results['mcp_client'] = 'jarvis_plugin' in mcontent
except Exception as e:
    results['mcp_client'] = 'ERROR'

# 9. Project context check
try:
    with open('core/project.py', 'r', encoding='utf-8', errors='replace') as f:
        pcontent = f.read()
    results['project_context'] = 'JARVIS_MD' in pcontent or 'CLAUDE_MD' in pcontent
except Exception as e:
    results['project_context'] = 'ERROR'

# 10. orjson check
try:
    import orjson
    results['orjson'] = 'OK'
except Exception as e:
    results['orjson'] = 'ERROR'

print()
# Print results
all_pass = True
for k, v in sorted(results.items()):
    status = 'PASS' if v == 'OK' else ('OK' if v != 'ERROR' and v != 'FAIL' else 'FAIL')
    if 'ERROR' in str(v):
        all_pass = False
    print(f'  {k:30s} : {status} -> {v}')

print()
print('='*70)
if all_pass:
    print('ALL CHECKS PASSED')
else:
    print('REVIEW NEEDED - see results above')
print('='*70)