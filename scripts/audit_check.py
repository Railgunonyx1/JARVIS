import sys, os, py_compile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

py_files = [
    r'core\config.py', r'core\planner.py', r'core\cog_error_handler.py',
    r'core\health.py', r'core\failure_analyzer.py', r'core\async_utils.py',
    r'core\exceptions.py',
]

print('CODE AUDIT: COMPILATION CHECK')
print('=' * 50)

all_ok = True
for f in py_files:
    path = ROOT / f
    try:
        py_compile.compile(str(path), doraise=True)
        print('  OK: ' + f)
    except py_compile.PyCompileError:
        print('  FAIL: ' + f)
        all_ok = False

print()
print('IMPORT CHECK')
print('=' * 50)

for mod in ['core.config', 'core.planner', 'core.health',
            'core.failure_analyzer', 'core.async_utils', 'core.exceptions']:
    try:
        __import__(mod)
        print('  OK: ' + mod)
    except Exception as e:
        print('FAIL: ' + mod + ': ' + str(e)[:30])

print()
if all_ok:
    print('ALL MODULES COMPILE SUCCESSFULLY')
else:
    print('SOME MODULES HAVE COMPILATION ISSUES')
