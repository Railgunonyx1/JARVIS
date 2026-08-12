import json

with open(r'C:\Users\aayan\Desktop\JARVIS\audits\bandit_current.json') as f:
    d = json.load(f)

totals = d.get('metrics', {}).get('_totals', {})
print(f"HIGH: {totals.get('SEVERITY.HIGH', 0)}")
print(f"MEDIUM: {totals.get('SEVERITY.MEDIUM', 0)}")
print(f"LOW: {totals.get('SEVERITY.LOW', 0)}")
print(f"loc: {totals.get('loc', 0)}")

# Per-file breakdown
for filepath, metrics in d.get('metrics', {}).items():
    if filepath == '_totals':
        continue
    sev = metrics.get('SEVERITY', {})
    high = sev.get('HIGH', 0)
    med = sev.get('MEDIUM', 0)
    low = sev.get('LOW', 0)
    if high > 0 or med > 0 or low > 0:
        print(f"  {filepath}: HIGH={high} MEDIUM={med} LOW={low}")
