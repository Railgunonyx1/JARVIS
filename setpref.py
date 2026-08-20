import sys
sys.path.insert(0, r"C:\Users\aayan\Desktop\JARVIS")
from core.inference_engine.model_router import get_model_router
r = get_model_router()
r.setPreference("speed")
print(r._preference)