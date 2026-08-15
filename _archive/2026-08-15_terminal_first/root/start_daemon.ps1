cd 'C:\Users\aayan\Desktop\JARVIS'
$env:PYTHONPATH = 'C:\Users\aayan\Desktop\JARVIS'
$python = 'C:\Users\aayan\AppData\Local\Programs\Python\Python311\python.exe'
& $python -m daemon.server start --project-dir 'C:\Users\aayan\Desktop\JARVIS'