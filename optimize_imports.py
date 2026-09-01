#!/usr/bin/env python
import sys

with open('cli/main.py', 'r', encoding='utf-8', errors='replace') as f:
    content = f.read()

# The exact text to replace (lines 35-39)
old_text = '''os.environ.setdefault("HF_HUB_DISABLE_PROGRESS_BARS", "1")
os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")
os.environ.setdefault("TRANSFORMERS_NO_ADVISORY_WARNINGS", "1")
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
warnings.filterwarnings("ignore")'''

new_text = '''os.environ.setdefault("HF_HUB_DISABLE_PROGRESS_BARS", "1")
os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")
os.environ.setdefault("TRANSFORMERS_NO_ADVISORY_WARNINGS", "1")
# Additional silence for library progress bars and telemetry before any provider is imported.
os.environ.setdefault("TRANSFORMERS_VERBOSITY", "error")
os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "3")
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
warnings.filterwarnings("ignore")'''

if old_text in content:
    new_content = content.replace(old_text, new_text)
    with open('cli/main.py', 'w', encoding='utf-8') as f:
        f.write(new_content)
    print('Import optimization added successfully')
else:
    print('Old text not found, showing actual content:')
    # Show lines 35-42
    with open('cli/main.py', 'r', encoding='utf-8', errors='replace') as f:
        lines = f.readlines()
    for i in range(34, 43):
        print(f'L{i}: {lines[i-1].rstrip()}')
PYEOF