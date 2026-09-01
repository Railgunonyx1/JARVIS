#!/usr/bin/env python
"""Integrate skills catalog search with memory system."""

import os
import sys
sys.path.insert(0, '.')

print("="*60)
print("SKILLS CATALOG SEARCH INTEGRATION")
print("="*60)

catalog_dir = r'C:\Users\aayan\Desktop\JARVIS\skills\catalog'

# Build a searchable index of all skills
skill_index = {}
total_skills = 0

for filename in sorted(os.listdir(catalog_dir)):
    if not filename.endswith('.md'):
        continue
    
    filepath = os.path.join(catalog_dir, filename)
    with open(filepath, 'r', encoding='utf-8', errors='replace') as f:
        content = f.read()
    
    # Extract skill entries (lines with **skill_name**)
    import re
    skill_entries = re.finditer(r'\*\*([^**]+)\*\*', content)
    
    for match in skill_entries:
        skill_name = match.group(1).strip()
        if not skill_name or len(skill_name) < 3:
            continue
        
        # Extract description (first line after the bold)
        # Find the line after the bold marker
        lines = content.split('\n')
        desc = ""
        for i, line in enumerate(lines):
            if f'**{skill_name}**' in line:
                # Look at lines after this
                for j in range(i+1, min(i+5, len(lines))):
                    next_line = lines[j].strip()
                    if next_line and not next_line.startswith('|') and not next_line.startswith('*') and len(next_line) > 5:
                        desc = next_line[:100]
                        break
                break
        
        # Extract repo info
        repo_match = re.search(r'\(([^)]+\)', content[content.find(skill_name):content.find(skill_name)+100])
        repo = repo_match.group(1).strip() if repo_match else ""
        
        # Store in index
        if skill_name not in skill_index:
            skill_index[skill_name] = []
        
        skill_index[skill_name].append({
            "filename": filename,
            "repo": repo,
            "description": desc,
            "source_file": filename
        })
        total_skills += 1

# Remove duplicates (same skill in multiple files)
for skill in skill_index:
    # Keep only unique entries
    seen = set()
    unique_entries = []
    for entry in skill_index[skill]:
        key = (entry["repo"], entry["description"])
        if key not in seen:
            seen.add(key)
            unique_entries.append(entry)
    skill_index[skill] = unique_entries

# Print summary
print(f"Skills catalog index built:")
print(f"  Total skills indexed: {total_skills}")
print(f"  Unique skill names: {len(skill_index)}")
print()

# Show top 10 searchable skills
print("Top searchable skills:")
for i, (skill, entries) in enumerate(list(skill_index.items())[:10]):
    entry = entries[0]
    print(f"  {i+1}. **{skill}** - {desc[:60] if desc else ''} - {entry['repo']}")

# Save index for agent use
index_file = os.path.join(catalog_dir, "search_index.json")
with open(index_file, 'w', encoding='utf-8') as f:
    import json
    # Convert any non-serializable types
    serializable_index = {}
    for skill, entries in skill_index.items():
        serializable_index[skill] = [
            {k: (v["description"][:80] if "description" in v and v["description"] else "") for k, v in entry.items()}
            for entry in entries
        ]
    json.dump(serializable_index, f, indent=2)

print(f"\nSearch index saved to: {index_file}")
print(f"  Unique skills: {len(skill_index)}")
print("="*60)