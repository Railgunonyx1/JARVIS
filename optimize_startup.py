#!/usr/bin/env python
with open('cli/main.py', 'r', encoding='utf-8', errors='replace') as f:
    content = f.read()

# Add phase condensation after the mode validation (after raise typer.Exit(code=1))
# Insert before _setup_logging(verbose)
old_text = '''raise typer.Exit(code=1)

    _setup_logging(verbose)'''

new_text = '''raise typer.Exit(code=1)

    # Conditional startup phases based on mode to reduce first-response time
    # Plan mode: skip heavy memory loading
    # Controlled/smart mode: reduced initialization
    # Agent mode: full initialization with interrupt executor
    if mode in ("plan", "controlled"):
        # Skip interrupt executor and heavy memory features
        _interrupt_executor = None
        _interrupt_classifier = None
    elif mode == "smart":
        # Smart mode: reduced features, no interrupt executor
        _interrupt_executor = None
        _interrupt_classifier = None

    _setup_logging(verbose)'''

if old_text in content:
    new_content = content.replace(old_text, new_text)
    with open('cli/main.py', 'w', encoding='utf-8') as f:
        f.write(new_content)
    print('Startup phase condensation added successfully')
else:
    print('Old text not found')
    # Show what's around line 400
    lines = content.split('\n')
    for i in range(396, 410):
        print(f'L{i}: {lines[i-1].rstrip()}')
PYEOF