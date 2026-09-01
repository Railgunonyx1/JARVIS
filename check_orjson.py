import subprocess
result = subprocess.run(['grep', '-r', 'orjson', '.'], capture_output=True, text=True, cwd='C:\\Users\\aayan\\Desktop\\JARVIS')
print('stdout:', result.stdout)
print('stderr:', result.stderr)