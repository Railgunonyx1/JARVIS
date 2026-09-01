import os, json
path = r'C:\Users\aayan\Desktop\JARVIS\skills\manifests'
files = sorted([f for f in os.listdir(path) if f.endswith('.json')])
print('Total manifest files:', len(files))
for f in files:
    full = os.path.join(path, f)
    with open(full, 'r', encoding='utf-8', errors='replace') as fh:
        data = json.load(fh)
    name = data.get('name', 'N/A')
    tools = data.get('tools', [])
    tags = data.get('tags', [])
    version = data.get('version', 'N/A')
    risk = data.get('risk', 'N/A')
    tout = data.get('timeout', 'N/A')
    pref = data.get('preferred_models', 'N/A')
    tags_str = str(tags)[:60] if tags else None
    print(f"{f}: name={name}, tools={len(tools)}, tags={tags_str}, version={version}, risk={risk}, timeout={tout}, preferred={str(pref)[:30] if pref != 'N/A' else None}")