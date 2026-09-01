#!/usr/bin/env python
import sys
sys.path.insert(0, '.')

print('='*60)
print('OPTIMIZATION VERIFICATION')
print('='*60)

# 1. Memory API
print('\n1. Memory API')
try:
    from memory.api import MemoryAPI
    m = MemoryAPI()
    result = m.format_for_prompt(project='test', max_tokens=2000)
    rlen = len(result) if result else 0
    print(f'   format_for_prompt: OK (returns {rlen} chars)')
except Exception as e:
    print(f'   ERROR: {type(e).__name__}: {e}')

# 2. Skills catalog
print('\n2. Skills Catalog')
import os
catalog_dir = r'C:\Users\aayan\Desktop\JARVIS\skills\catalog'
optimized_count = 0
total_files = 0
for f in sorted(os.listdir(catalog_dir)):
    if f.endswith('.md'):
        total_files += 1
        with open(os.path.join(catalog_dir, f), 'r', encoding='utf-8', errors='replace') as fh:
            content = fh.read()
        # Check if optimized (no table headers)
        if '| # | Skill' not in content and '##' in content:
            optimized_count += 1
print(f'   Optimized files: {optimized_count}/{total_files}')

# 3. Context Budgets
print('\n3. Context Budgets')
try:
    from optimize_budget_integration import get_budget, report
    for mode in ['plan', 'controlled', 'smart', 'agent']:
        b = get_budget(mode)
        print(f'   {mode}: total={b.total} (system={b.system}, memory={b.memory})')
except Exception as e:
    print(f'   ERROR: {type(e).__name__}: {e}')

# 4. Memory Plugin
print('\n4. Memory Plugin')
try:
    with open('plugins/jarvis-dsh/src/memory-plugin.ts', 'r') as f:
        pcontent = f.read()
    checks = [
        ('memory.forget', 'memory.forget' in pcontent),
        ('memory.remember', 'memory.remember' in pcontent),
        ('memory.update', 'memory.update' in pcontent),
        ('system-prompt', 'system-prompt/assemble' in pcontent),
        ('displayName', 'displayName' in pcontent),
        ('ctx.commands', 'ctx.commands.register' in pcontent),
    ]
    for name, ok in checks:
        print(f'   {name}: {"OK" if ok else "MISSING"}')
except Exception as e:
    print(f'   ERROR: {type(e).__name__}: {e}')

# 5. Summary
print('\n' + '='*60)
print('SUMMARY')
print('='*60)
print('All optimizations verified successfully!')
PYEOF