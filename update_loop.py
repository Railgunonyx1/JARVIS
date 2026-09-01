#!/usr/bin/env python
with open('core/agent/loop.py', 'r', encoding='utf-8', errors='replace') as f:
    lines = f.readlines()

# Check file length
print(f'File has {len(lines)} lines')

# Update lines 662-663 (1-indexed, so indices 661-662 in 0-indexed lines list)
if len(lines) > 662:
    # Line 662 (1-indexed) = lines[661] (0-indexed)
    # Original: "                if len(response.tool_calls) > self.max_tool_calls_per_step:"
    new_line_661 = '                _tool_call_limit = getattr(self, "_adaptive_tool_limit", self.max_tool_calls_per_step)\n'
    lines[661] = new_line_661
    
    # Line 663 (1-indexed) = lines[662] (0-indexed) 
    # Original: "                    self.logger.record(trace_id, events.TOOL_FAILED, {"
    new_line_662 = '                if len(response.tool_calls) > _tool_call_limit:\n'
    lines[662] = new_line_662
    
    # Keep the error record line but adjust
    if len(lines) > 663:
        lines[663] = '                    self.logger.record(trace_id, events.TOOL_FAILED, {\n'
    
    with open('core/agent/loop.py', 'w', encoding='utf-8') as f:
        f.writelines(lines)
    print('Updated lines 662-663 to use adaptive tool limit')
else:
    print(f'File only has {len(lines)} lines, expected at least 663')