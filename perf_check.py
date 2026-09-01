import re
from pathlib import Path

core_dir = Path('core')
issues = []
for pyfile in core_dir.rglob('*.py'):
    try:
        content = pyfile.read_text(encoding='utf-8', errors='ignore')
        if 'json.loads' in content:
            issues.append((str(pyfile), 'json.loads found'))
        if 'json.dumps' in content:
            issues.append((str(pyfile), 'json.dumps found'))
        if '.format(' in content and 'f"' not in content:
            issues.append((str(pyfile), '.format() found'))
    except:
        pass

print(f'Files with json operations: {len(issues)}')
for f, issue in issues[:20]:
    print(f'  {issue}: {f}')