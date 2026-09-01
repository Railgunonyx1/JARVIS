import json, orjson

# Check event_store.py
with open("C:\\Users\\aayan\\Desktop\\JARVIS\\core\\event_store.py", "r") as f:
    content = f.read()
    json_usage = content.count("json.")
    print(f"event_store.py: json. count = {json_usage}")

# Check decision_logger.py
with open("C:\\Users\\aayan\\Desktop\\JARVIS\\core\\decision_logger.py", "r") as f:
    content = f.read()
    json_usage = content.count("json.")
    print(f"decision_logger.py: json. count = {json_usage}")

# Check store.py
with open("C:\\Users\\aayan\\Desktop\\JARVIS\\core\\store.py", "r") as f:
    content = f.read()
    json_usage = content.count("json.")
    print(f"store.py: json. count = {json_usage}")

# Check core/agent/loop.py
with open("C:\\Users\\aayan\\Desktop\\JARVIS\\core\\agent\\loop.py", "r") as f:
    content = f.read()
    json_usage = content.count("json.")
    print(f"core/agent/loop.py: json. count = {json_usage}")