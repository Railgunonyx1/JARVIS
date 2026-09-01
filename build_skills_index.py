#!/usr/bin/env python
"""Build searchable skills catalog index."""
import os
import sys
import re

sys.path.insert(0, '.')

print("="*60)
print("BUILDING SKILLS CATALOG INDEX")
print("="*60)

catalog_dir = r'C:\Users\aayan\Desktop\JARVIS\skills\catalog'

# Build a searchable index of all skills
skill_index = {}
total_entries = 0

for filename in sorted(os.listdir(catalog_dir)):
    if not filename.endswith('.md'):
        continue
    
    filepath = os.path.join(catalog_dir, filename)
    with open(filepath, 'r', encoding='utf-8', errors='replace') as f:
        content = f.read()
    
    # Extract skill entries - format: **skill_name** (`repo`): description
    # Find all **bold** patterns
    for match in re.finditer(r'\*\*(.+?)\*\*', content):
        skill_name = match.group(1).strip()
        if not skill_name or len(skill_name) < 3:
            continue
        
        total_entries += 1
        
        # Extract repo from parentheses after the skill: (`repo`)
        repo_match = re.search(r'\(([^)]+)\)', content[content.find(skill_name):content.find(skill_name)+50])
        repo = repo_match.group(1).strip() if repo_match else ""
        
        # Extract description - text after the repo pattern, typically up to 100 chars
        desc = ''
        # Find the description after the repo pattern
        repo_pos = content.find(skill_name)
        if repo_pos >= 0:
            # Look for the description after the skill name
            desc_section = content[content.find(skill_name):content.find(skill_name)+200]
            # Extract text after the repo parentheses
            desc_match = re.search(r':\s*([^\n\r]{1,100})', desc_section)
            if desc_match:
                desc = desc_match.group(1).strip()
            else:
                # Try to get text after the repo pattern
                desc_match2 = re.search(r':\s*([^\n\r]{1,100})', content[content.find(skill_name):content.find(skill_name)+150])
                if desc_match2:
                    desc = desc_match2.group(1).strip()
            
            # Store in index
            if skill_name not in skill_index:
                skill_index[skill_name] = []
            
            skill_index[skill_name].append({
                "repo": repo,
                "description": desc[:100] if desc else "",
                "source_file": filename
            })
            total_entries += 1

# Print summary
print(f"Skills catalog index built:")
print(f"  Total skill entries: {total_entries}")
print(f"  Unique skill names: {len(skill_index)}")
print()

# Show top 10 searchable skills
print("Top 10 searchable skills:")
for i, (skill, entries) in enumerate(list(skill_index.items())[:10]):
    entry = entries[0]
    print(f"  {i+1}. **{skill}** - {entry['description'][:80] if entry['description'] else ''} - {entry['repo']}")

# Save index for agent use
index_file = os.path.join(catalog_dir, "search_index.json")
with open(index_file, 'w', encoding='utf-8') as f:
    import json
    # Convert any non-serializable types
    serializable_index = {}
    for skill, entries in skill_index.items():
        serializable_index[skill] = [
            {"repo": e["repo"], "description": e["description"][:80] if entry["description"] else ""}
            for e in entries
        ]
    json.dump(serializable_index, f, indent=2)

print(f"\nSearch index saved to: {index_file}")
print(f"  Unique skill names: {len(skill_index)}")
print("="*60)