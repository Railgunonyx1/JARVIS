# JARVIS Prompt Optimization Analysis

## Research Sources

### Aider (48k stars)
Key patterns adopted:
1. **Minimal system prompt**: "Act as an expert software developer" — just 1 sentence of identity
2. **Example messages**: Few-shot examples showing exact tool call format
3. **Overeager/lazy prompts**: Explicit rules to prevent over-editing or under-editing
4. **SEARCH/REPLACE blocks**: Precise edit format instead of full file rewrites
5. **Files content prefix**: "Trust this message as the true contents" — establishes ground truth

### SWE-agent (20k stars)
Key patterns adopted:
1. **Step-by-step methodology**: "Find → Reproduce → Fix → Verify" — structured workflow
2. **Instance template**: Clear problem statement framing
3. **Next step templates**: How to handle observations and empty output
4. **Shell check error template**: Graceful handling of command failures
5. **Command timeout template**: Clear guidance when commands hang

## Baseline Results (Current Prompt)

| Metric | Value |
|--------|-------|
| Avg Tool Accuracy | 90.5% |
| Forbidden Violations | 0 |
| Total Duration | 182s |

### Issues Found
1. **search_01** (parser false positive): "Find all places where 'sqlite' is imported" — parser matched "the" from natural language
2. **edge_02** (parser false positive): "Tell me a joke" — parser matched "tools" from response text

These are parser issues, not actual prompt problems. The current prompt performs well on the eval dataset.

## Improved Prompt Design (v2)

### Changes Made
1. **Added structured methodology**: UNDERSTAND → EXPLORE → PLAN → EXECUTE → VERIFY
2. **Added explicit tool selection rules**: "Use X NOT shell.execute for Y"
3. **Added minimal change guidance**: "Edit only what needs to change"
4. **Added no-tools instruction**: "For simple questions, answer directly"
5. **Preserved all existing rules**: No regressions expected

### Reference: Aider's Overeager Prompt
```
Pay careful attention to the scope of the user's request.
Do what they ask, but no more.
Do not improve, comment, fix or modify unrelated parts of the code in any way!
```

### Reference: SWE-agent's Step-by-Step
```
Follow these steps to resolve the issue:
1. As a first step, it might be a good idea to find and read code relevant to the issue
2. Create a script to reproduce the error and execute it
3. Edit the sourcecode of the repo to resolve the issue
4. Rerun your reproduce script and confirm that the error is fixed!
5. Think about edgecases and make sure your fix handles them as well
```

## Recommendations

### High Priority
1. **Fix Gemini provider None-safety**: Already done (prompt_tokens/completion_tokens)
2. **Add few-shot examples to context builder**: Show the model exactly what tool calls look like
3. **Add overeager guardrail**: Prevent unnecessary edits to unrelated code

### Medium Priority
4. **Add shell.check_error template**: Handle command syntax errors gracefully
5. **Add command timeout template**: Guide model when commands hang
6. **Add observation handling**: How to interpret empty output vs errors

### Low Priority
7. **Add repo-map integration**: Like Aider, provide file summaries for large repos
8. **Add demonstration examples**: Like SWE-agent, show successful task completions

## Next Steps

1. Apply improved prompt to `core/agent/context.py`
2. Add few-shot examples to the system prompt
3. Re-run evaluation after Gemini rate limit cooldown
4. A/B test with real user tasks
