import sys
sys.path.insert(0, r'C:\Users\aayan\Desktop\deepseek_harness')
from deepseek_memory import DeepSeekMemory, remember, recall, forget

mem = DeepSeekMemory()

# Add information
mem.add('project_name', 'JARVIS MK-X Automation')
mem.add('preferred_model', 'gemini-2.5-flash')

# Recall
val = mem.recall('project_name')
print('project_name:', val['value'] if val else 'Not found')

# List all
items = mem.list_all()
print('List all:')
for item in items:
    key = item['key']
    value = item['entry']['value']
    print(f'  {key}: {value}')

# Remove
forget('preferred_model')

# Check empty
val2 = forget('project_name')  # This is wrong, should use recall then check
# Actually let me just check if recall returns None
val_check = forget('nonexistent_key')  # This will return False
print('Remove nonexistent:', val_check)

# Check recall after removal
val_check2 = mem.recall('project_name')
print('project_name after removal:', val_check2)