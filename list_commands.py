import re
with open(r'C:\Users\aayan\Desktop\JARVIS\cli\main.py', 'r', encoding='utf-8', errors='replace') as f:
    content = f.read()
# Find all 'elif line' patterns with command names
pattern = r'elif line == "\/([^"]+)"'
matches = re.findall(pattern, content)
print('Exact command matches (after /):')
for m in matches[:60]:
    print(f'  /{m}')