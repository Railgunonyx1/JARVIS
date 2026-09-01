#!/usr/bin/env python
import sys
sys.path.insert(0, '.')
from core.context.budget import ContextBudget, DEFAULT_BUDGET

# Create mode-specific budget presets
budgets = {
    'plan': ContextBudget(
        system=8000,
        memory=8000,
        files=20000,
        messages=15000,
        response=10000,
    ),
    'controlled': ContextBudget(
        system=9000,
        memory=12000,
        files=25000,
        messages=15000,
        response=10000,
    ),
    'smart': ContextBudget(
        system=9500,
        memory=14000,
        files=28000,
        messages=15000,
        response=10000,
    ),
    'agent': ContextBudget(
        system=10000,
        memory=15000,
        files=30000,
        messages=15000,
        response=10000,
    ),
    'default': DEFAULT_BUDGET,
}

# Print the budgets for verification
for mode, budget in budgets.items():
    print(f'{mode}: system={budget.system}, memory={budget.memory}, files={budget.files}, messages={budget.messages}, response={budget.response}, total={budget.total}')

print()
print('DEFAULT_BUDGET total:', DEFAULT_BUDGET.total)