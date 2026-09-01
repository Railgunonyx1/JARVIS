import os

path = r'C:\Users\aayan\Desktop\JARVIS\skills\catalog'

# Read current README
readme_path = os.path.join(path, 'README.md')
with open(readme_path, 'r', encoding='utf-8', errors='replace') as f:
    readme = f.read()

# Stubs to remove (11-line files that duplicate topics in longer files)
stubs_to_remove = [
    '03-devops-infrastructure.md',    # duplicate of 04-devops-infrastructure.md
    '06-web-development.md',          # duplicate of 03-web-development.md
    '07-mobile-development.md',       # duplicate of 11-mobile-development.md
    '04-security-privacy.md',         # duplicate of 06-security.md
    '09-database-storage.md',         # duplicate of 09-databases.md
]

# Count remaining files
all_md = [f for f in os.listdir(path) if f.endswith('.md')]
remaining = [f for f in all_md if f not in stubs_to_remove]
remaining_count = len(remaining)

# Unique categories after dedup
categories_after_dedup = {
    'AI/ML Frameworks': '00-ai-ml-engineering.md, 01-ai-ml-frameworks.md, 01-code-generation.md',
    'Developer Tools': '02-developer-tools.md',
    'Web Development': '03-web-development.md',  # 06 removed
    'DevOps/Infrastructure': '04-devops-infrastructure.md',  # 03 removed
    'Data Science': '05-data-science.md',
    'Security': '06-security.md',  # 04 removed
    'Productivity': '07-productivity.md',
    'Programming Languages': '08-programming-languages.md, 08-systems-programming.md',
    'Databases': '09-databases.md',  # 09-database-storage removed
    'APIs/Services': '10-apis-services.md',
    'Documentation': '10-documentation-writing.md, 15-documentation.md',
    'Mobile Development': '11-mobile-development.md',  # 07 removed
    'Game Development': '12-game-development.md',
    'Blockchain/Web3': '13-blockchain-web3.md',
    'IoT/Hardware': '14-iot-hardware.md',
    'Research/Analysis': '14-research-analysis.md, 15-creative-design.md',
    'Specialized Tools': '16-specialized-tools.md',
    'Additional Repos': '17-additional-repos.md',
}

print(f"Current total .md files: {len(all_md)}")
print(f"Files after removing stubs: {remaining_count}")
print(f"Unique categories after dedup: {len(categories_after_dedup)}")
print("\nStubs to remove:")
for s in stubs_to_remove:
    full = os.path.join(path, s)
    lines = 0
    if os.path.exists(full):
        with open(full, 'r', encoding='utf-8', errors='replace') as f:
            lines = len(f.read().split('\n'))
        print(f"  {s}: {lines} lines - WILL REMOVE")
        os.remove(full)
    else:
        print(f"  {s}: not found already removed")

# Updated README text
new_readme = """# JARVIS MK-X GitHub Repository Catalog

This catalog contains curated GitHub repositories organized by category.
These repos can be used as skills, tools, and references for JARVIS.

## Categories

""".strip()

cat_num = 1
for cat, files in categories_after_dedup.items():
    new_readme += f"{cat_num}. {cat} ({len(files.split(', '))} repos)\n"
    cat_num += 1

new_readme += "\n*Full catalog: {} entries. Use memory recall to search.*".format(remaining_count)

# Write updated README
with open(readme_path, 'w', encoding='utf-8') as f:
    f.write(new_readme)

print(f"\nUpdated README.md with {remaining_count} entries across {len(categories_after_dedup)} categories")
print("Removed stub files:", stubs_to_remove)