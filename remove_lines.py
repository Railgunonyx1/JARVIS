with open('core/executor.py', 'r') as f:
    lines = f.readlines()

# Remove lines 585-588 (1-indexed) which are the problematic lines
# 0-indexed: delete indices 584, 585, 586, 587
# These are: 'if speak:', 'speak(...)', 'replan_attempts += 1', ''

new_lines = lines[:584]  # Keep through line 583 (return msg)

with open('core/executor.py', 'w') as f:
    f.writelines(new_lines)
print('Removed lines 585-588')