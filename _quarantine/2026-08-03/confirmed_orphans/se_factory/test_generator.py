"""Test Generator — Auto-generate test cases from code.

Analyzes functions/classes and generates appropriate unit tests.
"""
import logging
import re
import time
from typing import Optional, Dict, Any, List
from dataclasses import dataclass, field

logger = logging.getLogger("se_factory.test_generator")


@dataclass
class TestSuite:
    """Generated test suite."""
    source_file: str = ""
    test_code: str = ""
    test_count: int = 0
    coverage_estimate: float = 0.0
    generation_ms: float = 0.0


class TestGenerator:
    """Generate unit tests from Python source code."""

    def __init__(self):
        self._history: List[Dict[str, Any]] = []

    def generate_tests(self, source_code: str, source_file: str = "") -> TestSuite:
        """Generate test cases for the given source code."""
        start = time.time()

        functions = self._extract_functions(source_code)
        classes = self._extract_classes(source_code)

        test_lines = ['"""Auto-generated test suite."""\n', 'import pytest\n']
        test_count = 0

        for func_name, params in functions:
            test_lines.extend(self._generate_function_tests(func_name, params))
            test_count += 1

        for class_name in classes:
            test_lines.extend(self._generate_class_tests(class_name))
            test_count += 1

        elapsed_ms = (time.time() - start) * 1000
        test_code = "\n".join(test_lines)

        suite = TestSuite(
            source_file=source_file,
            test_code=test_code,
            test_count=test_count,
            coverage_estimate=min(test_count * 10, 100),
            generation_ms=elapsed_ms,
        )

        self._history.append({"file": source_file, "tests": test_count, "ms": elapsed_ms})
        return suite

    def _extract_functions(self, code: str) -> List[tuple]:
        results = []
        for match in re.finditer(r'def\s+(\w+)\s*\(([^)]*)\):', code):
            name = match.group(1)
            params = [p.strip().split(':')[0].strip() for p in match.group(2).split(',') if p.strip() and p.strip() != 'self']
            results.append((name, params))
        return results

    def _extract_classes(self, code: str) -> List[str]:
        return re.findall(r'class\s+(\w+)', code)

    def _generate_function_tests(self, func_name: str, params: List[str]) -> List[str]:
        tests = []
        test_name = f"test_{func_name}"

        # Basic invocation test
        args = ", ".join(["None" for _ in params])
        tests.append(f"\ndef {test_name}():")
        tests.append(f'    """Test {func_name}."""')
        if params:
            tests.append(f"    result = {func_name}({args})")
        else:
            tests.append(f"    result = {func_name}()")
        tests.append("    assert result is not None")

        # Edge case test for empty/None inputs
        if params:
            tests.append(f"\ndef {test_name}_edge_cases():")
            tests.append(f'    """Test {func_name} edge cases."""')
            tests.append(f"    result = {func_name}({', '.join(['None' for _ in params])})")
            tests.append("    assert result is not None")

        return tests

    def _generate_class_tests(self, class_name: str) -> List[str]:
        tests = []
        tests.append(f"\ndef test_{class_name.lower()}_instantiation():")
        tests.append(f'    """Test {class_name} can be instantiated."""')
        tests.append(f"    instance = {class_name}()")
        tests.append(f"    assert instance is not None")
        return tests

    def get_stats(self) -> Dict[str, Any]:
        total = len(self._history)
        total_tests = sum(h["tests"] for h in self._history)
        return {
            "files_processed": total,
            "total_tests_generated": total_tests,
            "avg_tests_per_file": round(total_tests / max(total, 1), 1),
        }


_test_gen_instance: Optional[TestGenerator] = None


def get_test_generator() -> TestGenerator:
    global _test_gen_instance
    if _test_gen_instance is None:
        _test_gen_instance = TestGenerator()
    return _test_gen_instance
