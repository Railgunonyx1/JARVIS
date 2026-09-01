import os, re

def find_patterns(directory, patterns):
    found = []
    for root, dirs, files in os.walk(directory):
        for f in files:
            if f.endswith('.py'):
                path = os.path.join(root, f)
                try:
                    with open(path, 'r', errors='ignore') as fh:
                        content = fh.read()
                        for i, line in enumerate(content.split('\n'), 1):
                            for p in patterns:
                                if p.lower() in line.lower():
                                    found.append((path, i, line.strip()))
                except Exception as e:
                    pass
    return found

patterns = ['TODO', 'FIXME', 'XXX']
results = find_patterns('core', patterns)
for r in results[:20]:
    print(f'{r[0]}:{r[1]}: {r[2][:80]}')