@echo off
cd /d C:\Users\aayan\Desktop\JARVIS
set PYTHONPATH=C:\Users\aayan\Desktop\JARVIS
"C:\Users\aayan\Desktop\JARVIS\venv\Scripts\pythonw.exe" -u web\server.py > "C:\Users\aayan\Desktop\JARVIS\flask-sched.log" 2>&1
