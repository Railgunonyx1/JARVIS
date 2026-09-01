import re
with open('core/agent/loop.py') as f:
    content = f.read()
# Check for various optimization-related patterns
patterns = {
    'orjson': content.count('orjson'),
    'json.loads': content.count('json.loads'),
    'json.dumps': content.count('json.dumps'),
    'detect_task_type': content.count('detect_task_type'),
    'detect_task_type_with_confidence': content.count('detect_task_type_with_confidence'),
    'select_model': content.count('select_model'),
    'TaskType': content.count('TaskType'),
    'TaskType.': content.count('TaskType.'),
    'QUICK': content.count('QUICK'),
    'HEAVY': content.count('HEAVY'),
    'CONVERSATIONAL': content.count('CONVERSATIONAL'),
    'CODING': content.count('CODING'),
    'RESEARCH': content.count('RESEARCH'),
    'WRITING': content.count('WRITING'),
    'REASONING': content.count('REASONING'),
    'cascade_mode': content.count('cascade_mode'),
    'cascade_router': content.count('cascade_router'),
    'cascade_worker': content.count('cascade_worker'),
    'cascade_heavy': content.count('cascade_heavy'),
    'direct_handle_count': content.count('direct_handle_count'),
    'escalation_count': content.count('escalation_count'),
    'draft_verify_count': content.count('draft_verify_count'),
    'deterministic_count': content.count('deterministic_count'),
}
for k, v in patterns.items():
    if v > 0:
        print(f"'{k}': {v}")