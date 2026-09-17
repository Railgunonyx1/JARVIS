"""Tolerant JSON repair for LLM tool-call arguments.

Research basis (goose#8272, earendil/pi#952, partial-json patterns): models
emit tool arguments that fail strict ``json.loads`` for predictable reasons —
markdown fences, Unicode curly quotes, trailing reasoning text after the
object, and truncation from token caps or dropped stream tails. The old
behavior at every parse site was ``json.loads`` fail → ``{}`` → the tool
EXECUTES with empty arguments, which is worse than failing: it is silently
wrong.

The repair ladder, cheapest first:

1. Strip markdown/code fences around the payload.
2. Normalize Unicode curly quotes to ASCII (JSON requires them).
3. Strict parse of the cleaned string.
4. Trim trailing non-JSON text (reasoning appended after the object) by
   scanning for the last balanced close from the first open.
5. Balance truncated JSON: close open strings, then brackets, then braces
   (partial-json's completion strategy).
6. Give up: caller receives an explicit error instead of a silent ``{}``.

``repair_json_args`` returns ``(arguments, error)``. On success ``error``
is empty. On failure ``arguments`` is ``{}`` and ``error`` describes why —
callers must NOT execute a tool on failure; route it to the model as a
malformed-tool failure so it can retry.
"""

from __future__ import annotations

import json

# Reserved key used to carry a parse failure inside a ToolCall's arguments
# so it flows through the existing tool_service MALFORMED_TOOL machinery.
JSON_ERROR_KEY = "__json_error"
# Companion key carrying the original (capped) raw arguments string so the
# retry nudge can show the model exactly what it emitted.
JSON_RAW_KEY = "__json_raw"

_MAX_ERR_SNIPPET = 120
_MAX_RAW_SNIPPET = 300


def _strip_fences(text: str) -> str:
    """Remove markdown/code fences: ```json ... ``` or ``` ... ```."""
    t = text.strip()
    if not t.startswith("```"):
        return t
    # Drop the opening fence (with optional language tag) and closing fence.
    first_nl = t.find("\n")
    if first_nl == -1:
        return t
    body = t[first_nl + 1:]
    end = body.rfind("```")
    if end != -1:
        body = body[:end]
    return body.strip()


_CURLY_DOUBLE = {"\u201c": '"', "\u201d": '"'}  # “ ” — risky as delimiters


def _normalize_quotes(text: str) -> str:
    """Replace curly double quotes ONLY outside string interiors.

    Inside strings, curly quotes are legal content — normalizing them
    would mutate values (file text, queries, names). Outside strings they
    can only be delimiters a model used in place of ASCII quotes.
    """
    if not any(c in text for c in _CURLY_DOUBLE):
        return text
    out: list[str] = []
    in_str = False
    escape = False
    for c in text:
        if in_str:
            if escape:
                escape = False
            elif c == "\\":
                escape = True
            elif c == '"':
                in_str = False
            out.append(c)
        else:
            if c == '"':
                in_str = True
            out.append(_CURLY_DOUBLE.get(c, c))
    return "".join(out)


def _escape_controls_in_strings(text: str) -> str:
    """Escape raw \n/\r/\t inside JSON strings (LLMs emit these literally;
    strict JSON requires escapes). String-aware so legal whitespace outside
    strings is untouched."""
    out: list[str] = []
    in_str = False
    escape = False
    repl = {"\n": "\\n", "\r": "\\r", "\t": "\\t"}
    for c in text:
        if in_str:
            if escape:
                escape = False
            elif c == "\\":
                escape = True
            elif c == '"':
                in_str = False
            elif c in repl:
                out.append(repl[c])
                continue
        elif c == '"':
            in_str = True
        out.append(c)
    return "".join(out)


def _parse_balanced_at(text: str) -> dict | None:
    """Parse the first balanced JSON object in ``text`` (skips leading
    reasoning text and trailing text after the closing brace)."""
    start = text.find("{")
    if start == -1:
        return None
    depth = 0
    in_str = False
    escape = False
    for i in range(start, len(text)):
        c = text[i]
        if in_str:
            if escape:
                escape = False
            elif c == "\\":
                escape = True
            elif c == '"':
                in_str = False
            continue
        if c == '"':
            in_str = True
        elif c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                try:
                    obj = json.loads(text[start:i + 1])
                    return obj if isinstance(obj, dict) else None
                except (TypeError, ValueError):
                    return None
    return None


def _detect_truncation(text: str) -> bool:
    """True when ``text`` ends mid-string or with unclosed brackets.

    Truncation (token cap / dropped stream tail) is intentionally NOT
    repaired: balancing would fabricate a complete-looking object from
    partial data — e.g. a ``filesystem.write`` executing with silently
    truncated content. The model must retry instead.
    """
    stack: list[str] = []
    in_str = False
    escape = False
    for c in text:
        if in_str:
            if escape:
                escape = False
            elif c == "\\":
                escape = True
            elif c == '"':
                in_str = False
            continue
        if c == '"':
            in_str = True
        elif c in "{[":
            stack.append(c)
        elif c in "}]":
            if stack:
                stack.pop()
    return bool(stack) or in_str


def repair_json_args(raw: str) -> tuple[dict, str]:
    """Attempt tolerant parse of LLM tool-call argument JSON.

    Returns ``(arguments, error)`` — exactly one of the two is meaningful.
    """
    if raw is None:
        return {}, "arguments were None"
    text = _escape_controls_in_strings(_normalize_quotes(_strip_fences(str(raw))))
    if not text.strip():
        return {}, ""  # empty args are legitimately {}
    try:
        obj = json.loads(text)
        if isinstance(obj, dict):
            return obj, ""
        return {"value": obj}, ""
    except (TypeError, ValueError) as exc:
        first_err = str(exc)[:_MAX_ERR_SNIPPET]

    # Trailing reasoning text after a well-formed object.
    obj = _parse_balanced_at(text)
    if obj is not None:
        return obj, ""

    # Truncation: explicit failure, never execute on guessed/partial data.
    if _detect_truncation(text):
        return {}, "arguments truncated (stream cut or token cap) — retry the call"

    return {}, first_err or "unparseable arguments"


def arguments_with_error_marker(raw: str) -> tuple[dict, bool]:
    """Convenience for parse sites: returns ``(arguments, ok)``.

    On success ``ok`` is True and ``arguments`` is the repaired dict. On
    failure ``ok`` is False and ``arguments`` carries ``JSON_ERROR_KEY`` plus
    ``JSON_RAW_KEY`` (capped original) so the tool service can reject the
    call as MALFORMED_TOOL with a targeted retry nudge instead of executing
    it with silently-empty arguments.
    """
    args, err = repair_json_args(raw)
    if err:
        return {JSON_ERROR_KEY: err, JSON_RAW_KEY: str(raw)[:_MAX_RAW_SNIPPET]}, False
    return args, True


__all__ = [
    "JSON_ERROR_KEY",
    "JSON_RAW_KEY",
    "arguments_with_error_marker",
    "repair_json_args",
]
