import sys, os, py_compile

sys.path.insert(0, r'C:\Users\aayan\Desktop\JARVIS')

py_files = [
    r'core\config.py', r'core\planner.py', r'core\executor.py',
    r'core\cog_error_handler.py', r'core\health.py', 
    r'core\failure_analyzer.py', r'core\async_utils.py', r'core\exceptions.py',
    r'ui\providers.py', r'workflows\goal_decomposer.py'
]

print('CODE AUDIT: COMPILATION CHECK')
print('='*50)

all_ok = True
for f in py_files:
    path = os.path.join(r'C:\Users\aayan\Desktop\JARVIS', f)
    try:
        py_compile.compile(path, doraise=True)
        print('  OK: ' + f)
    except py_compile.PyCompileError:
        print('  ❌ ' + f)
        all_ok = False

print()
print('IMPORT CHECK')
print('='*50)

for mod in ['core.config', 'core.planner', 'core.executor', 'core.health',
            'core.failure_analyzer', 'core.async_utils', 'core.exceptions',
            'workflows.goal_decomposer']:
    try:
        __import__(mod)
        print('  OK: ' + mod)
    except Exception as e:
        print('❌ ' + mod + ': ' + str(e)[:30])

print()
if all_ok:
    print('ALL MODULES COMPILE AND IMPORT SUCCESSFULLY')
else:
    print('SOME MODULES HAVE ISSUES')