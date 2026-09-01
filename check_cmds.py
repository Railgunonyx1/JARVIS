with open('plugins/jarvis-dsh/src/memory-plugin.ts') as f:
    content = f.read()
import re
for pattern in ['command', 'ctx.commands', 'registerCommands']:
    matches = [(m.start(), content[max(0,m.start()-50):m.end()+50]) for m in re.finditer(pattern, content, re.IGNORECASE)]
    if matches:
        print('Pattern "%s": %d matches' % (pattern, len(matches)))
        for pos, ctx in matches[:2]:
            print('  ...%s...' % ctx)
print('Done')