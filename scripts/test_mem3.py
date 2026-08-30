import sys
sys.path.insert(0, r'C:\Users\aayan\Desktop\deepseek_harness')
from deepseek_memory import DeepSeekMemory, remember, recall, forget

mem = DeepSeekMemory()
mem.add('project_name', 'JARVIS MK-X Automation')
mem.add('preferred_model', 'gemini-2.5-flash')

val = mem.recall('project_name')
v = val['value'] if val else 'Not found'
print('project_name:', v)

items = mem.list_all()
for item in items:
    k = item['key']
    v = item['entry']['value']
    print(f'  {k}: {v}')

forget('preferred_model')

val_check = forget('nonexistent_key')
print('Remove nonexistent:', val_check)

val_check2 = mem.recall('project_name')
v2 = val_check['value'] if val_check else 'Not found'
print('project_name after removal:', v2)