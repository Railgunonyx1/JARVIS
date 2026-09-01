# Read tools/__init__.py and find build_default_registry
with open(r'C:\Users\aayan\Desktop\JARVIS\tools\__init__.py', 'r', encoding='utf-8') as f:
    content = f.read()
# Find the build_default_registry function
idx = content.find('def build_default_registry')
if idx >= 0:
    # Get the function definition
    print(content[idx:idx+3000])
else:
    print('Not found')