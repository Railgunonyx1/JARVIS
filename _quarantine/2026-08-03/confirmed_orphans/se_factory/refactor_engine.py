"""Refactor Engine — Suggest and apply code refactorings.

Detects common code smells and suggests improvements.
"""
import logging
import re
import time
from typing import Optional, Dict, Any, List
from dataclasses import dataclass, field

logger = logging.getLogger("se_factory.refactor_engine")


@dataclass
class RefactorSuggestion:
    """A suggested refactoring."""
    rule: str
    line: int
    severity: str  # "info", "warning", "suggestion"
    message: str
    old_code: str = ""
    suggested_code: str = ""


class RefactorEngine:
    """Detect code smells and suggest refactorings."""

    RULES = [
        {"name": "long_function", "pattern": r"def\s+\w+.*?:", "max_lines": 50, "severity": "warning",
         "message": "Function exceeds {max} lines — consider breaking into smaller functions"},
        {"name": "deep_nesting", "pattern": r"^\s{16,}", "severity": "warning",
         "message": "Deep nesting detected — consider early returns or extraction"},
        {"name": "magic_string", "pattern": r'["\'][a-zA-Z]{20,}["\']', "severity": "info",
         "message": "Long string literal — consider extracting to constant"},
        {"name": "duplicate_import", "pattern": r"^(import|from)\s+", "severity": "info",
         "message": "Potential duplicate import"},
        {"name": "long_parameter_list", "pattern": r"def\s+\w+\(([^)]{50,})\):", "severity": "warning",
         "message": "Long parameter list — consider using a dataclass or dict"},
        {"name": "global_usage", "pattern": r"\bglobal\s+\w+", "severity": "warning",
         "message": "Global variable usage — consider refactoring to class or parameter"},
        {"name": "bare_return", "pattern": r"^\s*return\s*$", "severity": "info",
         "message": "Bare return — consider returning a value or removing"},
    ]

    def __init__(self):
        self._history: List[Dict[str, Any]] = []

    def analyze(self, code: str, file_path: str = "") -> List[RefactorSuggestion]:
        """Analyze code and return refactoring suggestions."""
        suggestions = []
        lines = code.split("\n")

        for rule in self.RULES:
            for i, line in enumerate(lines, 1):
                if re.search(rule["pattern"], line):
                    suggestions.append(RefactorSuggestion(
                        rule=rule["name"],
                        line=i,
                        severity=rule["severity"],
                        message=rule["message"],
                        old_code=line.strip(),
                    ))

        self._history.append({
            "file": file_path[:100],
            "suggestions": len(suggestions),
            "by_severity": {
                "warning": sum(1 for s in suggestions if s.severity == "warning"),
                "info": sum(1 for s in suggestions if s.severity == "info"),
            },
        })

        return suggestions

    def apply_quick_fixes(self, code: str) -> str:
        """Apply safe automatic refactorings."""
        # Remove trailing whitespace
        code = re.sub(r'[ \t]+$', '', code, flags=re.MULTILINE)
        # Remove duplicate blank lines
        code = re.sub(r'\n{3,}', '\n\n', code)
        return code

    def get_stats(self) -> Dict[str, Any]:
        total = len(self._history)
        total_suggestions = sum(h["suggestions"] for h in self._history)
        return {
            "files_analyzed": total,
            "total_suggestions": total_suggestions,
            "avg_per_file": round(total_suggestions / max(total, 1), 1),
        }


_refactor_instance: Optional[RefactorEngine] = None


def get_refactor_engine() -> RefactorEngine:
    global _refactor_instance
    if _refactor_instance is None:
        _refactor_instance = RefactorEngine()
    return _refactor_instance
