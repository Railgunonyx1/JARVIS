#!/usr/bin/env python
with open('core/agent/loop.py', 'r', encoding='utf-8', errors='replace') as f:
    content = f.read()

# Find the tool call truncation section and add token tracking after it
old_section = '''# Track token usage for each section
                self._token_usage["messages"] += estimate_tokens(
                    [m for m in messages if m.get("role") in ("user", "assistant", "tool")]
                )
                # Estimate memory tokens from the format_for_prompt output
                if hasattr(self, '_last_memory_prompt'):
                    self._token_usage["memory"] = estimate_tokens(self._last_memory_prompt)

                # Safety: if the LLM keeps making tool calls without ever producing
                # a text response, inject a nudge after 5 consecutive tool-only iterations.'''

new_section = '''# Track token usage for each section
                from core.context.budget import estimate_tokens
                self._token_usage["messages"] += estimate_tokens(
                    [m for m in messages if m.get("role") in ("user", "assistant", "tool")]
                )
                # Estimate memory tokens from the format_for_prompt output
                if hasattr(self, '_last_memory_prompt'):
                    self._token_usage["memory"] = estimate_tokens(self._last_memory_prompt)

                # Safety: if the LLM keeps making tool calls without ever producing
                # a text response, inject a nudge after 5 consecutive tool-only iterations.'''

if old_section in content:
    new_content = content.replace(old_section, new_section)
    with open('core/agent/loop.py', 'w', encoding='utf-8') as f:
        f.write(new_content)
    print('Token usage tracking updated')
else:
    print('Old section not found')
    # Try to find the safety section
    idx = content.find('Safety: if the LLM keeps making')
    if idx >= 0:
        print('Found at index', idx)
        print(content[max(0,idx-50):idx+100])