#!/usr/bin/env python
import os

# Optimize skills catalog files
catalog_dir = r'C:\Users\aayan\Desktop\JARVIS\skills\catalog'

for filename in sorted(os.listdir(catalog_dir)):
    if not filename.endswith('.md'):
        continue
    
    filepath = os.path.join(catalog_dir, filename)
    with open(filepath, 'r', encoding='utf-8', errors='replace') as f:
        content = f.read()
    
    # Check if this is a table-based file (has | # | Skill |)
    if '| # | Skill' not in content:
        continue
    
    lines = content.split('\n')
    # Find table start (after header row)
    table_start = None
    for i, line in enumerate(lines):
        if '| # | Skill' in line:
            table_start = i + 2  # skip header and separator
            break
    
    if table_start is None:
        continue
    
    # Parse rows
    rows = []
    for i in range(table_start, len(lines)):
        line = lines[i].strip()
        if not line or line.startswith('|---'):
            continue
        parts = [p.strip() for p in line.split('|') if p.strip()]
        if len(parts) >= 4:
            num = parts[0] if parts[0].isdigit() else ''
            skill = parts[1] if len(parts) > 1 else ''
            repo = parts[2] if len(parts) > 2 else ''
            desc = parts[3] if len(parts) > 3 else ''
            jarvis = parts[4] if len(parts) > 4 else ''
            rows.append((num, skill, repo, desc, jarvis))
    
    if not rows:
        continue
    
    # Create optimized version
    # Keep the title, replace table with top entries list
    optimized = '# ' + filename.replace('.md', '').replace('-', ' ').title() + '\n\n'
    
    # Add top 8 most relevant entries (based on JARVIS use or first 8)
    optimized += 'Curated GitHub repositories.\n\n'
    
    for num, skill, repo, desc, jarvis in rows[:8]:
        # Shorten description to first phrase, 80 chars max
        brief = desc.split('.')[0][:80] if desc else ''
        jarvis_text = f' - {jarvis}' if jarvis and jarvis != 'JARVIS Use' else ''
        optimized += f'- **{skill}** (`{repo}`): {brief}{jarvis_text}\n'
    
    optimized += f'\n*Full catalog: {len(rows)} entries. Use memory recall to search.*\n'
    
    # Write optimized version
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(optimized)

print('Skills catalog optimization complete')