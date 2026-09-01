import re
with open(r'C:\Users\aayan\Desktop\JARVIS\cli\main.py', 'r', encoding='utf-8', errors='replace') as f:
    content = f.read()
# Find all 'startswith' commands
pattern = r'elif line\.startswith\(/\"([^"]+)\"'
matches = re.findall(pattern, content)
print('Startswith command prefixes:')
for m in matches[:40]:
    print(f'  /{m}')