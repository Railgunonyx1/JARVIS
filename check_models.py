import urllib.request, json
try:
    with urllib.request.urlopen("http://127.0.0.1:11434/api/tags", timeout=3) as r:
        data = json.loads(r.read())
        for m in data.get("models", []):
            size_gb = m.get("size", 0) / (1024**3)
            params = m.get("details", {}).get("parameter_size", "?")
            quant = m.get("details", {}).get("quantization_level", "?")
            print(f"  {m['name']:30s} {size_gb:5.1f}GB  {params}  {quant}")
except Exception as e:
    print(f"Error: {e}")
