"""Quick compute — the zero-network calculator family.

Derived from sukeesh/Jarvis's plugin taxonomy (categories 7 "Unit Conversions"
and 6 "Random Generators"): the small, exact utilities an assistant should
answer instantly — arithmetic, unit conversion, base conversion, a strong
password — without a model round-trip or a new browser tab.

Every function here is hermetic: stdlib only, no filesystem, no network, no
side effects. ``calc.safe`` never ``eval``s — arithmetic is validated against
an AST whitelist (literals, the four-and-a-half operators, a handful of math
functions), so model-supplied strings can never escape into execution.
"""

from __future__ import annotations

import ast
import math
import secrets
import string
from typing import Any

from tools.schema import ToolResult

_MAX_INPUT_LEN = 400
_MAX_EXPONENT = 1000


# ────────────────────────────────────────────────────────────── calc.safe ──

_ALLOWED_FUNCS: dict[str, Any] = {
    "sqrt": math.sqrt, "abs": abs, "round": round,
    "min": min, "max": max, "floor": math.floor, "ceil": math.ceil,
    "log": math.log, "log2": math.log2, "log10": math.log10,
    "sin": math.sin, "cos": math.cos, "tan": math.tan,
    "asin": math.asin, "acos": math.acos, "atan": math.atan,
    "degrees": math.degrees, "radians": math.radians,
}
_ALLOWED_CONSTS: dict[str, float] = {"pi": math.pi, "e": math.e, "tau": math.tau}
_ALLOWED_BINOPS = (ast.Add, ast.Sub, ast.Mult, ast.Div, ast.FloorDiv, ast.Mod, ast.Pow)
_ALLOWED_UNARY = (ast.UAdd, ast.USub)


def _fmt_num(value: float | int) -> str:
    if isinstance(value, int) or (isinstance(value, float) and value.is_integer() and abs(value) < 1e15):
        return str(int(value))
    return f"{value:.10g}"


def _eval_node(node: ast.AST) -> float | int:
    if isinstance(node, ast.Expression):
        return _eval_node(node.body)
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)) and not isinstance(node.value, bool):
        return node.value
    if isinstance(node, ast.Name) and node.id in _ALLOWED_CONSTS:
        return _ALLOWED_CONSTS[node.id]
    if isinstance(node, ast.BinOp) and isinstance(node.op, _ALLOWED_BINOPS):
        left, right = _eval_node(node.left), _eval_node(node.right)
        if isinstance(node.op, ast.Pow):
            if abs(right) > _MAX_EXPONENT:
                raise ValueError(f"exponent too large (max {_MAX_EXPONENT})")
            return left ** right
        if isinstance(node.op, ast.Add):
            return left + right
        if isinstance(node.op, ast.Sub):
            return left - right
        if isinstance(node.op, ast.Mult):
            return left * right
        if isinstance(node.op, ast.Div):
            return left / right
        if isinstance(node.op, ast.FloorDiv):
            return left // right
        return left % right  # ast.Mod
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, _ALLOWED_UNARY):
        value = _eval_node(node.operand)
        return value if isinstance(node.op, ast.UAdd) else -value
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in _ALLOWED_FUNCS:
        if node.keywords:
            raise ValueError("keyword arguments not supported")
        args = [_eval_node(a) for a in node.args]
        if not args:
            raise ValueError(f"{node.func.id}() needs arguments")
        return _ALLOWED_FUNCS[node.func.id](*args)
    raise ValueError(f"unsupported expression element: {type(node).__name__}")


def calc_safe(args: dict[str, Any]) -> ToolResult:
    """Evaluate an arithmetic expression via an AST whitelist — never eval()."""
    expr = str(args.get("expression") or "").strip()
    if not expr:
        return ToolResult(success=False, error="expression is required — e.g. (2+3)*7 or sqrt(144)")
    if len(expr) > _MAX_INPUT_LEN:
        return ToolResult(success=False, error=f"expression too long (max {_MAX_INPUT_LEN} chars)")
    try:
        tree = ast.parse(expr, mode="eval")
    except SyntaxError as exc:
        return ToolResult(success=False, error=f"could not parse expression: {exc.msg}")
    try:
        result = _eval_node(tree)
    except ZeroDivisionError:
        return ToolResult(success=False, error="division by zero")
    except (ValueError, OverflowError) as exc:
        return ToolResult(success=False, error=str(exc))
    return ToolResult(success=True, output=f"{expr} = {_fmt_num(result)}")


# ──────────────────────────────────────────────────────────── convert.unit ──

# Each category: canonical unit -> (factor_to_canonical, aliases).
# Temperature is special-cased below.
_UNITS: dict[str, dict[str, tuple[float, tuple[str, ...]]]] = {
    "length": {"m": (1.0, ("meter", "metre", "meters", "metres")),
               "mm": (0.001, ("millimeter", "millimetre", "millimeters")),
               "cm": (0.01, ("centimeter", "centimetre", "centimeters")),
               "km": (1000.0, ("kilometer", "kilometre", "kilometers")),
               "in": (0.0254, ("inch", "inches")),
               "ft": (0.3048, ("foot", "feet")),
               "yd": (0.9144, ("yard", "yards")),
               "mi": (1609.344, ("mile", "miles")),
               "nmi": (1852.0, ("nautical mile", "nauticalmile"))},
    "mass": {"kg": (1.0, ("kilogram", "kilograms", "kilo", "kilos")),
             "mg": (1e-6, ("milligram", "milligrams")),
             "g": (0.001, ("gram", "grams")),
             "t": (1000.0, ("tonne", "tonnes", "metric ton")),
             "oz": (0.028349523125, ("ounce", "ounces")),
             "lb": (0.45359237, ("pound", "pounds", "lbs")),
             "stone": (6.35029318, ("stones",))},
    "data": {"byte": (1.0, ("bytes", "B")),
             "bit": (0.125, ("bits",)),
             "kb": (1e3, ("kilobyte", "kilobytes")),
             "mb": (1e6, ("megabyte", "megabytes")),
             "gb": (1e9, ("gigabyte", "gigabytes")),
             "tb": (1e12, ("terabyte", "terabytes")),
             "kib": (1024.0, ("kibibyte",)),
             "mib": (1024.0 ** 2, ("mebibyte",)),
             "gib": (1024.0 ** 3, ("gibibyte",))},
    "speed": {"mps": (1.0, ("m/s", "meters per second", "metres per second")),
              "kmh": (1.0 / 3.6, ("km/h", "kph", "kilometers per hour")),
              "mph": (0.44704, ("mi/h", "miles per hour")),
              "knot": (1852.0 / 3600.0, ("knots", "kn")),
              "ftps": (0.3048, ("ft/s", "feet per second"))},
    "time": {"s": (1.0, ("sec", "secs", "second", "seconds")),
             "ms": (0.001, ("millisecond", "milliseconds")),
             "min": (60.0, ("minute", "minutes")),
             "h": (3600.0, ("hour", "hours", "hr", "hrs")),
             "day": (86400.0, ("days",)),
             "week": (604800.0, ("weeks",))},
    "volume": {"l": (1.0, ("liter", "litre", "liters", "litres")),
               "ml": (0.001, ("milliliter", "millilitre", "milliliters")),
               "gal": (3.785411784, ("gallon", "gallons", "usgal")),
               "qt": (0.946352946, ("quart", "quarts")),
               "pint": (0.473176473, ("pints",)),
               "cup": (0.2365882365, ("cups",)),
               "floz": (0.0295735295625, ("fluid ounce", "fluid ounces"))},
    "area": {"m2": (1.0, ("square meter", "square metre", "square meters")),
             "km2": (1e6, ("square kilometer", "square kilometers")),
             "ft2": (0.09290304, ("square foot", "square feet", "sqft")),
             "acre": (4046.8564224, ("acres",)),
             "hectare": (10000.0, ("hectares", "ha"))},
}

# Alias -> canonical, per category (built once at import).
_ALIASES: dict[str, dict[str, str]] = {}
for _cat, _units in _UNITS.items():
    table: dict[str, str] = {}
    for _canon, (_factor, _names) in _units.items():
        table[_canon.lower()] = _canon
        for _alias in _names:
            table[_alias.lower()] = _canon
    _ALIASES[_cat] = table

_TEMPS = {"c": ("celsius", "°c", "centigrade"),
          "f": ("fahrenheit", "°f"),
          "k": ("kelvin",)}


def _resolve_temp(unit: str) -> str | None:
    unit = unit.lower().strip()
    if unit in _TEMPS:
        return unit
    for canon, names in _TEMPS.items():
        if unit in names:
            return canon
    return None


def _resolve_unit(category: str, unit: str) -> str | None:
    return _ALIASES[category].get(unit.lower().strip().replace("²", "2").replace("³", "3"))


def convert_unit(args: dict[str, Any]) -> ToolResult:
    """Convert a value between units: length, mass, temperature, data, speed, time, volume, area."""
    raw = args.get("value")
    category = str(args.get("category") or "").lower().strip()
    from_u = str(args.get("from") or "").strip()
    to_u = str(args.get("to") or "").strip()
    if raw is None or not from_u or not to_u:
        return ToolResult(success=False, error="value, from, and to are required")
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return ToolResult(success=False, error=f"not a number: {raw!r}")
    if not category:
        # Auto-detect: find a category that knows both units.
        known = [c for c in _UNITS if _resolve_unit(c, from_u) and _resolve_unit(c, to_u)]
        if len(known) == 1:
            category = known[0]
        elif not known and _resolve_temp(from_u) and _resolve_temp(to_u):
            category = "temperature"
        else:
            return ToolResult(
                success=False,
                error="category is required (or units are unknown) — one of: "
                + ", ".join(list(_UNITS) + ["temperature"]),
            )
    if category == "temperature":
        src, dst = _resolve_temp(from_u), _resolve_temp(to_u)
        if not src or not dst:
            return ToolResult(success=False, error=f"unknown temperature unit (use C, F, or K): {from_u if not src else to_u}")
        celsius = {"c": value, "f": (value - 32) * 5 / 9, "k": value - 273.15}[src]
        result = {"c": celsius, "f": celsius * 9 / 5 + 32, "k": celsius + 273.15}[dst]
    else:
        if category not in _UNITS:
            return ToolResult(success=False, error=f"unknown category: {category}")
        src, dst = _resolve_unit(category, from_u), _resolve_unit(category, to_u)
        if not src or not dst:
            missing = from_u if not src else to_u
            return ToolResult(success=False, error=f"unknown {category} unit: {missing}")
        result = value * _UNITS[category][src][0] / _UNITS[category][dst][0]
    return ToolResult(success=True, output=f"{_fmt_num(value)} {from_u} = {_fmt_num(result)} {to_u}")


# ──────────────────────────────────────────────────────────── convert.base ──

_BASE_NAMES = {2: "binary", 8: "octal", 10: "decimal", 16: "hexadecimal"}


def convert_base(args: dict[str, Any]) -> ToolResult:
    """Convert an integer between bases (2–36); reports the common bases alongside."""
    digits = str(args.get("value") or "").strip()
    from_base = int(args.get("from_base") or 10)
    to_base = args.get("to_base")
    if not digits:
        return ToolResult(success=False, error="value is required")
    digits = digits.replace("_", "").lstrip("+")
    negative = digits.startswith("-")
    if negative:
        digits = digits[1:]
    if not 2 <= from_base <= 36:
        return ToolResult(success=False, error=f"from_base must be 2–36, got {from_base}")
    try:
        number = int(digits, from_base)
    except ValueError:
        return ToolResult(success=False, error=f"{digits!r} is not a valid base-{from_base} number")
    if negative:
        number = -number
    sign = "-" if number < 0 else ""
    magnitude = abs(number)

    def to_str(n: int, base: int) -> str:
        chars, out = string.digits + string.ascii_lowercase, ""
        while n:
            out = chars[n % base] + out
            n //= base
        return sign + (out or "0")

    if to_base is not None:
        to_base = int(to_base)
        if not 2 <= to_base <= 36:
            return ToolResult(success=False, error=f"to_base must be 2–36, got {to_base}")
        label = _BASE_NAMES.get(to_base, f"base {to_base}")
        return ToolResult(success=True, output=f"{digits} (base {from_base}) = {to_str(magnitude, to_base)} ({label})")
    lines = [f"{digits} (base {from_base}) ="]
    for base in (2, 8, 10, 16):
        lines.append(f"  {_BASE_NAMES[base]:<11} {to_str(magnitude, base)}")
    return ToolResult(success=True, output="\n".join(lines))


# ───────────────────────────────────────────────────────────── gen.password ──

_SETS = {
    "lower": string.ascii_lowercase,
    "upper": string.ascii_uppercase,
    "digits": string.digits,
    "symbols": "!@#$%^&*-_=+?",
}
_AMBIGUOUS = "O0oIl1|`'\"{}[]()/\\;:,.<>"  # excluded with exclude_ambiguous=True


def gen_password(args: dict[str, Any]) -> ToolResult:
    """Generate a strong password with secrets — never random, never stored, never logged."""
    try:
        length = int(args.get("length") or 20)
    except (TypeError, ValueError):
        return ToolResult(success=False, error="length must be an integer")
    if not 8 <= length <= 128:
        return ToolResult(success=False, error="length must be 8–128")

    pools = [chars for key, chars in _SETS.items() if args.get(key, True)]
    if not pools:
        return ToolResult(success=False, error="at least one character set must stay enabled")
    if args.get("exclude_ambiguous", True):
        pools = ["".join(c for c in pool if c not in _AMBIGUOUS) for pool in pools]

    alphabet = "".join(pools)
    # Guarantee one char per selected set, then fill from the combined alphabet.
    chars = [secrets.choice(pool) for pool in pools]
    chars += [secrets.choice(alphabet) for _ in range(length - len(chars))]
    # SystemRandom-backed Fisher–Yates (random.shuffle is fine with SystemRandom).
    rng = secrets.SystemRandom()
    rng.shuffle(chars)
    password = "".join(chars)

    entropy = length * math.log2(len(alphabet))
    return ToolResult(
        success=True,
        output=f"password: {password}\n"
        f"strength: ~{entropy:.0f} bits ({length} chars from a {len(alphabet)}-symbol alphabet)",
    )
