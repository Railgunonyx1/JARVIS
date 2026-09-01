with open('core/executor.py', 'r') as f:
    lines = f.readlines()

# Lines 585-588 (0-indexed: 584-587) need fixing
# The issue: lines 585-588 have extra indentation
# Line 585 (index 584): "if speak:" - should be 8 spaces indent
# Line 586 (index 585): "speak(...)" - should be 12 spaces indent (inside if)
# Line 587 (index 586): blank
# Line 588 (index 587): "replan_attempts += 1" - should be 8 spaces indent (same level as "if speak:")

# Let's fix the indentation
for i in [584, 585, 586, 587]:  # indices for lines 585-588
    # Remove 4 spaces of extra indentation
    lines[i] = lines[i].lstrip(' ')

with open('core/executor.py', 'w') as f:
    f.writelines(lines)
print('Fixed')