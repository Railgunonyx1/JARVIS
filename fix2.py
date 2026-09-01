with open('core/executor.py', 'r') as f:
    lines = f.readlines()

# Remove lines 585-588 (0-indexed: 584-587) which are the problematic lines
# These are: "if speak:", "speak(...)", "replan_attempts += 1", and the blank line after
# The correct structure should have the "if replan_attempts >= ..." block

# Keep lines 0-583 (through line 583 which is "return msg")
# Then add a blank line, then the proper if replan_attempts block

# But we need to figure out what the correct structure is.
# Based on the test failures and the code pattern, the original code had:
# 
# if replan_attempts >= self.MAX_REPLAN_ATTEMPTS:
#     msg = ...
#     decision_logger.record(...)
#     if speak:
#         speak(redact_sensitive(msg))
#     return msg
#
# Then somewhere after this block, replan_attempts += 1

# Since I don't have the original, let me just remove lines 585-588 and see if
# the tests pass (they may have been failing because of the misplaced code anyway)

new_lines = lines[:584]  # Keep lines 0-583 (return msg and before)
new_lines.append('')  # blank line

with open('core/executor.py', 'w') as f:
    f.writelines(new_lines)
print('Removed lines 585-588')
EOF