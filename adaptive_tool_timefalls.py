#!/usr/bin/env python
with open('core/agent/loop.py', 'r', encoding='utf-8', errors='replace') as f:
    content = f.read()

# Find the max_tool_calls_per_step definition and add adaptive logic after it
old_section = '''# Model-aware iteration limits: smaller models get fewer iterations
            _model_iterations = self.max_iterations
            _current_model = state.model or ""
            if any(s in _current_model for s in ("1.5b", "1b")):
                _model_iterations = min(_model_iterations, 5)
                _budgets["total"] = min(_budgets["total"], 20.0)
            elif "3b" in _current_model:
                _model_iterations = min(_model_iterations, 10)
                _budgets["total"] = min(_budgets["total"], 45.0)
            elif any(s in _current_model for s in ("4b", "7b")):
                _budgets["total"] = min(_budgets["total"], 60.0)'''

new_section = '''# Model-aware iteration limits: smaller models get fewer iterations
            _model_iterations = self.max_iterations
            _current_model = state.model or ""
            if any(s in _current_model for s in ("1.5b", "1b")):
                _model_iterations = min(_model_iterations, 5)
                _budgets["total"] = min(_budgets["total"], 20.0)
            elif "3b" in _current_model:
                _model_iterations = min(_model_iterations, 10)
                _budgets["total"] = min(_budgets["total"], 45.0)
            elif any(s in _current_model for s in ("4b", "7b")):
                _budgets["total"] = min(_budgets["total"], 60.0)

            # Adaptive tool timefalls: reduce max tool calls based on
            # model size, iteration count, and overall confidence
            _adaptive_tool_limit = self.max_tool_calls_per_step
            if _current_model and any(s in _current_model for s in ("1.5b", "1b")):
                # Small models: reduce tool calls significantly
                _adaptive_tool_limit = max(1, self.max_tool_calls_per_step - 3)
            elif any(s in _current_model for s in ("3b",)):
                # Medium models: moderate reduction
                _adaptive_tool_limit = max(2, self.max_tool_calls_per_step - 2)
            # Large models keep the full limit

            # Further reduce tool calls as iterations progress
            # (diminishing returns, risk of low-confidence calls)
            _progress_factor = (_model_iterations - state.iteration + 1) / _model_iterations
            _adaptive_tool_limit = max(1, int(_adaptive_tool_limit * _progress_factor))'''

if old_section in content:
    new_content = content.replace(old_section, new_section)
    with open('core/agent/loop.py', 'w', encoding='utf-8') as f:
        f.write(new_content)
    print('Adaptive tool timefalls added successfully')
else:
    print('Old section not found - showing first 50 chars around area:')
    idx = content.find('# Model-aware iteration limits')
    if idx >= 0:
        print(content[idx:idx+300])