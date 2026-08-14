import sys
sys.path.insert(0, r'C:\Users\aayan\Desktop\JARVIS')
from daemon.lifecycle import daemon_status
import json
port = daemon_status(r'C:\Users\aayan\Desktop\JARVIS')
if port:
    print(json.dumps(port, indent=2))
else:
    print("No daemon running")