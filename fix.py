with open('core/executor.py', 'r') as f:
    lines = f.readlines()

# Fix line 586 (index 585): add 4 spaces to indent inside 'if speak:'
lines[585] = '    speak(redact_sensitive("Adjusting my approach, sir."))'

with open('core/executor.py', 'w') as f:
    f.writelines(lines)
print('Fixed indentation on line 586')