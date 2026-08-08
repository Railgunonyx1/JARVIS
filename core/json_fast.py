"""Fast JSON helpers — orjson-backed drop-in for stdlib json.

orjson serializes 4-12x faster than stdlib `json`; the `.decode()` here
returns str so existing f-string call sites keep working unchanged.
Falls back to stdlib json if orjson is not installed.
"""

try:
    import orjson

    def dumps(obj, *, default=None):
        if default is not None:
            return orjson.dumps(obj, default=default).decode("utf-8")
        return orjson.dumps(obj).decode("utf-8")

    def loads(s):
        return orjson.loads(s)

    ORJSON = True
except ImportError:  # pragma: no cover
    import json as _json

    def dumps(obj, *, default=None):
        return _json.dumps(obj, default=default)

    def loads(s):
        return _json.loads(s)

    ORJSON = False
