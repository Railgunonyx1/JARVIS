"""Wire protocol for the JARVIS daemon IPC.

Every message is an :class:`Envelope` with a fixed shape so the protocol can
grow (streaming, auth, compression, priority) without breaking older clients:

    {
        "version": 1,
        "id": "<request uuid, echoed in responses>",
        "type": "run" | "ping" | "stream.event" | "stream.result" | ...,
        "timestamp": <unix float>,
        "payload": {...}
    }

Framing is NDJSON: one compact JSON object per line. ``orjson`` is used when
available (it is installed), falling back to the stdlib ``json`` module.
Serialization is the pluggable seam for the future msgpack pass.
"""

from __future__ import annotations

import json
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

__all__ = [
    "PROTOCOL_VERSION",
    "MSG_AUTH",
    "MSG_PING",
    "MSG_STATUS",
    "MSG_RUN",
    "MSG_SET_MODE",
    "MSG_MEMORY_SEARCH",
    "MSG_MEMORY_ADD",
    "MSG_MODELS",
    "MSG_HISTORY",
    "MSG_SHUTDOWN",
    "MSG_PONG",
    "MSG_OK",
    "MSG_RESULT",
    "MSG_EVENT",
    "MSG_RUN_RESULT",
    "MSG_ERROR",
    "MSG_BUSY",
    "MSG_CANCEL",
    "MAX_FRAME_SIZE",
    "Envelope",
    "make_envelope",
    "encode_line",
    "decode_line",
]

PROTOCOL_VERSION = 1

MAX_FRAME_SIZE = 4 * 1024 * 1024

# Request message types (client -> daemon)
MSG_AUTH = "auth"
MSG_PING = "ping"
MSG_STATUS = "status"
MSG_RUN = "run"
MSG_SET_MODE = "set_mode"
MSG_MEMORY_SEARCH = "memory_search"
MSG_MEMORY_ADD = "memory_add"
MSG_MODELS = "models"
MSG_HISTORY = "history"
MSG_SHUTDOWN = "shutdown"
MSG_CANCEL = "cancel"

# Response message types (daemon -> client)
MSG_PONG = "pong"
MSG_OK = "ok"
MSG_RESULT = "result"
MSG_EVENT = "stream.event"      # one task observer event
MSG_RUN_RESULT = "stream.result"  # terminal frame for a run
MSG_ERROR = "error"
MSG_BUSY = "busy"


@dataclass
class Envelope:
    """One framed message on the wire."""

    type: str = ""
    id: str = ""
    payload: Dict[str, Any] = field(default_factory=dict)
    version: int = PROTOCOL_VERSION
    timestamp: float = field(default_factory=time.time)


def make_envelope(type_: str, payload: Optional[Dict[str, Any]] = None,
                  id_: str = "") -> Envelope:
    return Envelope(
        type=type_,
        id=id_ or uuid.uuid4().hex,
        payload=dict(payload or {}),
    )


def _dumps(data: Dict[str, Any]) -> str:
    try:
        import orjson  # type: ignore[import-not-found]

        return orjson.dumps(data).decode("utf-8")
    except Exception:
        return json.dumps(data, default=str)


def _loads(line: str) -> Dict[str, Any]:
    try:
        import orjson  # type: ignore[import-not-found]

        return orjson.loads(line)
    except Exception:
        return json.loads(line)


def encode_line(env) -> bytes:
    """Serialize an :class:`Envelope` (or an equivalent dict) as one NDJSON line."""
    data = dict(env) if isinstance(env, dict) else {
        "version": env.version,
        "id": env.id,
        "type": env.type,
        "timestamp": env.timestamp,
        "payload": env.payload,
    }
    return (_dumps(data) + "\n").encode("utf-8")


def decode_line(line: bytes) -> Envelope:
    if len(line) > MAX_FRAME_SIZE:
        raise ValueError(
            f"frame too large: {len(line)} bytes (max {MAX_FRAME_SIZE})"
        )
    data = _loads(line.decode("utf-8"))
    return Envelope(
        version=int(data.get("version", PROTOCOL_VERSION)),
        id=str(data.get("id", "")),
        type=str(data.get("type", "")),
        timestamp=float(data.get("timestamp", 0.0)),
        payload=dict(data.get("payload", {}) or {}),
    )
