"""Tests for the sukeesh/Jarvis-derived quick-compute family.

Hermetic by construction: pure stdlib computation — no network, no filesystem,
no subprocesses. calc.safe is additionally asserted to reject injection
attempts (it validates an AST whitelist, never eval()).
"""

from __future__ import annotations

import string
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools import build_default_registry  # noqa: E402
from tools.quick_compute import calc_safe, convert_base, convert_unit, gen_password  # noqa: E402


# ----------------------------------------------------------------- registry

def test_quick_compute_registered():
    registry = build_default_registry()
    for name in ("calc.safe", "convert.unit", "convert.base", "gen.password"):
        tool = registry.get(name)
        assert tool is not None, f"{name} missing from registry"
        assert tool.handler is not None
        assert tool.permission == "system.query"
        assert tool.risk == "safe"


# ---------------------------------------------------------------- calc.safe

def test_calc_basic_arithmetic():
    assert calc_safe({"expression": "(2+3)*7"}).output == "(2+3)*7 = 35"
    assert calc_safe({"expression": "10/4"}).output == "10/4 = 2.5"
    assert calc_safe({"expression": "2**10"}).output == "2**10 = 1024"
    assert calc_safe({"expression": "7 % 3"}).output == "7 % 3 = 1"
    assert calc_safe({"expression": "-5 + 2"}).output == "-5 + 2 = -3"


def test_calc_functions_and_constants():
    assert calc_safe({"expression": "sqrt(144)"}).output == "sqrt(144) = 12"
    assert "3.14159" in calc_safe({"expression": "round(pi, 5)"}).output
    assert calc_safe({"expression": "max(3, 7, 5)"}).output == "max(3, 7, 5) = 7"
    assert calc_safe({"expression": "floor(9.9)"}).output == "floor(9.9) = 9"


def test_calc_rejects_injection():
    """The whitelist must refuse anything that is not plain arithmetic."""
    payloads = (
        "__import__('os').system('echo pwned')",
        "().__class__.__mro__",
        "open('/etc/passwd').read()",
        "1 if True else 2",
        "[x for x in range(3)]",
        "lambda: 1",
        "exec('1')",
    )
    for payload in payloads:
        res = calc_safe({"expression": payload})
        assert res.success is False, payload


def test_calc_error_paths():
    assert calc_safe({}).success is False
    assert "zero" in calc_safe({"expression": "1/0"}).error.lower()
    assert calc_safe({"expression": "2**5000"}).success is False
    assert calc_safe({"expression": "2 +* 3"}).success is False
    assert calc_safe({"expression": "frobnicate(3)"}).success is False


# ------------------------------------------------------------- convert.unit

def test_unit_auto_detection():
    res = convert_unit({"value": 5, "from": "km", "to": "mi"})
    assert res.success and "3.1068" in res.output
    res = convert_unit({"value": 1, "from": "gb", "to": "mb"})
    assert res.success and "= 1000 mb" in res.output
    res = convert_unit({"value": 1, "from": "gib", "to": "mib"})
    assert res.success and "= 1024 mib" in res.output


def test_unit_temperature():
    assert "= 212 F" in convert_unit({"value": 100, "from": "C", "to": "F"}).output
    assert "= 273.15 k" in convert_unit({"value": 0, "from": "celsius", "to": "kelvin"}).output
    assert "= 98.6 f" in convert_unit({"value": 37, "from": "C", "to": "f"}).output


def test_unit_aliases_and_explicit_category():
    res = convert_unit({"value": 180, "from": "pounds", "to": "kg"})
    assert res.success and "81.6" in res.output
    res = convert_unit({"value": 90, "from": "kmh", "to": "mph", "category": "speed"})
    assert res.success and "55.9" in res.output


def test_unit_errors():
    assert convert_unit({"value": 1, "from": "km", "to": "lb"}).success is False  # no single category
    assert convert_unit({"value": 1, "from": "km", "to": "furlongs"}).success is False
    assert convert_unit({"value": "abc", "from": "km", "to": "mi"}).success is False
    assert convert_unit({"from": "km", "to": "mi"}).success is False


# ------------------------------------------------------------ convert.base

def test_base_overview():
    res = convert_base({"value": "FF", "from_base": 16})
    assert res.success
    assert "11111111" in res.output and "255" in res.output and "377" in res.output


def test_base_single_target():
    res = convert_base({"value": "255", "to_base": 36})
    assert res.success and "= 73 (base 36)" in res.output
    res = convert_base({"value": "1010", "from_base": 2, "to_base": 10})
    assert res.success and "= 10 (decimal)" in res.output


def test_base_negative_and_garbage():
    res = convert_base({"value": "-FF", "from_base": 16, "to_base": 10})
    assert res.success and res.output.endswith("-255 (decimal)")
    assert convert_base({"value": "ZZ", "from_base": 10}).success is False
    assert convert_base({"value": "10", "from_base": 1}).success is False
    assert convert_base({"value": "10", "to_base": 37}).success is False
    assert convert_base({}).success is False


# ------------------------------------------------------------ gen.password

def test_password_default_strength():
    res = gen_password({})
    assert res.success and res.output.startswith("password: ")
    pw = res.output.splitlines()[0].split(": ", 1)[1]
    assert len(pw) == 20
    assert "bits" in res.output  # entropy estimate reported


def test_password_length_bounds():
    assert gen_password({"length": 4}).success is False
    assert gen_password({"length": 500}).success is False
    assert len(gen_password({"length": 8}).output.splitlines()[0].split(": ")[1]) == 8
    assert len(gen_password({"length": 128}).output.splitlines()[0].split(": ")[1]) == 128


def test_password_charset_respected():
    res = gen_password({"length": 64, "lower": False, "upper": False, "symbols": False})
    pw = res.output.splitlines()[0].split(": ", 1)[1]
    assert pw and set(pw) <= set("23456789")  # digits only, ambiguous 0/1 excluded
    res = gen_password({"length": 64, "symbols": False, "exclude_ambiguous": False})
    pw = res.output.splitlines()[0].split(": ", 1)[1]
    assert set(pw) <= set(string.ascii_letters + string.digits)
    assert gen_password({"lower": False, "upper": False, "digits": False, "symbols": False}).success is False
