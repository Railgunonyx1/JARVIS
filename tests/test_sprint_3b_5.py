"""Quick verification for Sprint 3b (sandbox ShellMode) and Sprint 5 (skills)."""
from security.sandbox import Sandbox, ShellMode
from skills import build_default_skill_registry
from tools import build_default_registry

# --- Sprint 3b: Sandbox ShellMode ---
s = Sandbox()

# Classification tests
assert s._classify_shell_mode('git status') == ShellMode.DIRECT
assert s._classify_shell_mode('python -m pytest') == ShellMode.DIRECT
assert s._classify_shell_mode('ruff check .') == ShellMode.DIRECT
assert s._classify_shell_mode('echo hello') == ShellMode.CMD_C
assert s._classify_shell_mode('dir') == ShellMode.CMD_C
assert s._classify_shell_mode('git log | head -5') == ShellMode.CMD_C
assert s._classify_shell_mode('dir > output.txt') == ShellMode.CMD_C
assert s._classify_shell_mode('echo hello && echo world') == ShellMode.CMD_C
print('[OK] Classification')

# Execution tests
result = s.execute('echo hello')
assert result.success, f'echo failed: {result.stderr}'
assert result.shell_mode == ShellMode.CMD_C
assert 'hello' in result.stdout
print(f'[OK] echo: mode={result.shell_mode.value}, out={result.stdout.strip()!r}')

result2 = s.execute('python -c "print(42)"')
assert result2.success, f'python failed: {result2.stderr}'
assert result2.shell_mode == ShellMode.DIRECT
assert '42' in result2.stdout
print(f'[OK] python: mode={result2.shell_mode.value}, out={result2.stdout.strip()!r}')

# Verify to_dict includes shell_mode
d = result.to_dict()
assert 'shell_mode' in d
print(f'[OK] to_dict includes shell_mode={d["shell_mode"]}')

# --- Sprint 5: Skill Registry ---
sr = build_default_skill_registry()
tr = build_default_registry()
assert len(sr) == 5
print(f'[OK] {len(sr)} skills loaded')

for sk in sr.list_all():
    print(f'     {sk.name}: {sk.tool_names}')

warnings = sr.validate(tr)
assert not warnings, f'Unexpected warnings: {warnings}'
print('[OK] All skill tools registered')

print('\n=== SPRINT 3b + 5: ALL PASSED ===')
