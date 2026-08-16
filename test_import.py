import sys
print("Python version:", sys.version)
try:
    import websockets
    print("websockets: OK")
except ImportError:
    print("websockets: NOT INSTALLED")