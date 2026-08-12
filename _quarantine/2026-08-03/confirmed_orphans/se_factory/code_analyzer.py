"""Code Analyzer — Analyze code for complexity, quality, and patterns.

Provides static analysis, complexity metrics, and quality scoring.
"""
import logging
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger("se_factory.code_analyzer")


@dataclass
class AnalysisResult:
    """Result of code analysis."""
    file_path: str = ""
    language: str = "python"
    lines_of_code: int = 0
    complexity_score: float = 0.0  # 0-100 (lower = simpler)
    quality_score: float = 0.0    # 0-100 (higher = better)
    issues: list[dict[str, Any]] = field(default_factory=list)
    metrics: dict[str, Any] = field(default_factory=dict)
    suggestions: list[str] = field(default_factory=list)
    analysis_ms: float = 0.0


class CodeAnalyzer:
    """Static code analyzer for Python code quality and complexity."""

    PYTHON_COMPLEXITY_KEYWORDS = [
        "if", "elif", "else", "for", "while", "try", "except",
        "finally", "with", "and", "or", "not",
    ]

    QUALITY_RULES = [
        {"name": "no_bare_except", "pattern": r"except\s*:", "severity": "warning", "message": "Bare except clause"},
        {"name": "no_star_import", "pattern": r"from\s+\S+\s+import\s+\*", "severity": "warning", "message": "Wildcard import"},
        {"name": "has_docstring", "pattern": r'"""[^"]+"""', "severity": "info", "message": "Docstring present", "inverse": True},
        {"name": "no_print_debug", "pattern": r"print\s*\(", "severity": "info", "message": "Print statement (debug?)"},
        {"name": "no_todo", "pattern": r"#\s*TODO", "severity": "info", "message": "TODO comment"},
        {"name": "no_magic_numbers", "pattern": r"(?<!=)\s\d{3,}(?![\.\d])", "severity": "info", "message": "Large magic number"},
    ]

    def __init__(self):
        self._history: list[dict[str, Any]] = []

    def analyze_code(self, code: str, file_path: str = "", language: str = "python") -> AnalysisResult:
        """Analyze code and return quality/complexity metrics."""
        start = time.time()
        result = AnalysisResult(file_path=file_path, language=language)

        lines = code.split("\n")
        result.lines_of_code = len([l for l in lines if l.strip()])

        if language == "python":
            result.complexity_score = self._calculate_complexity(code)
            result.quality_score = self._calculate_quality(code, result)
            result.issues = self._find_issues(code)
            result.suggestions = self._generate_suggestions(result)

        result.metrics = {
            "lines_of_code": result.lines_of_code,
            "blank_lines": len([l for l in lines if not l.strip()]),
            "comment_lines": len([l for l in lines if l.strip().startswith("#")]),
            "function_count": len(re.findall(r"def\s+\w+", code)),
            "class_count": len(re.findall(r"class\s+\w+", code)),
            "import_count": len(re.findall(r"^(?:import|from)\s+", code, re.MULTILINE)),
            "avg_line_length": sum(len(l) for l in lines) / max(len(lines), 1),
        }

        result.analysis_ms = (time.time() - start) * 1000

        self._history.append({
            "file_path": file_path[:100],
            "lines": result.lines_of_code,
            "quality": result.quality_score,
            "complexity": result.complexity_score,
            "issues": len(result.issues),
        })

        return result

    def _calculate_complexity(self, code: str) -> float:
        """Calculate cyclomatic complexity (0-100 scale)."""
        complexity = 1
        for keyword in self.PYTHON_COMPLEXITY_KEYWORDS:
            complexity += len(re.findall(r'\b' + keyword + r'\b', code))

        lines = len(code.split("\n"))
        if lines > 0:
            complexity_per_line = complexity / lines
            score = min(complexity_per_line * 500, 100)
        else:
            score = 0
        return round(score, 1)

    def _calculate_quality(self, code: str, result: AnalysisResult) -> float:
        """Calculate quality score (0-100, higher = better)."""
        score = 100.0

        for issue in result.issues:
            if issue["severity"] == "error":
                score -= 15
            elif issue["severity"] == "warning":
                score -= 5
            elif issue["severity"] == "info":
                score -= 1

        metrics = result.metrics
        if metrics.get("comment_lines", 0) == 0 and metrics.get("lines_of_code", 0) > 10:
            score -= 10
        if metrics.get("function_count", 0) == 0 and metrics.get("class_count", 0) == 0:
            if metrics.get("lines_of_code", 0) > 20:
                score -= 5

        return max(0, min(100, round(score, 1)))

    def _find_issues(self, code: str) -> list[dict[str, Any]]:
        issues = []
        lines = code.split("\n")
        for i, line in enumerate(lines, 1):
            for rule in self.QUALITY_RULES:
                if re.search(rule["pattern"], line):
                    issues.append({
                        "line": i,
                        "severity": rule["severity"],
                        "message": rule["message"],
                        "rule": rule["name"],
                    })
        return issues

    def _generate_suggestions(self, result: AnalysisResult) -> list[str]:
        suggestions = []
        if result.complexity_score > 60:
            suggestions.append("High complexity detected — consider breaking into smaller functions")
        if result.quality_score < 70:
            suggestions.append("Quality score is below 70 — review flagged issues")
        if result.metrics.get("comment_lines", 0) == 0 and result.lines_of_code > 10:
            suggestions.append("No comments found — add docstrings or inline comments")
        if result.metrics.get("function_count", 0) == 0 and result.lines_of_code > 50:
            suggestions.append("No functions found — consider extracting reusable logic")
        issue_types = set(i["rule"] for i in result.issues)
        if "no_bare_except" in issue_types:
            suggestions.append("Replace bare except with specific exception types")
        if "no_star_import" in issue_types:
            suggestions.append("Replace wildcard imports with explicit imports")
        return suggestions

    def analyze_file(self, file_path: str) -> AnalysisResult:
        """Analyze a file on disk."""
        try:
            path = Path(file_path)
            code = path.read_text(encoding="utf-8")
            lang = path.suffix.lstrip(".")
            if lang not in ("py", "python"):
                lang = "python"
            return self.analyze_code(code, file_path=file_path, language=lang)
        except Exception as e:
            return AnalysisResult(file_path=file_path, error=str(e))

    def get_stats(self) -> dict[str, Any]:
        total = len(self._history)
        avg_quality = sum(h["quality"] for h in self._history) / max(total, 1)
        avg_complexity = sum(h["complexity"] for h in self._history) / max(total, 1)
        total_issues = sum(h["issues"] for h in self._history)
        return {
            "files_analyzed": total,
            "avg_quality_score": round(avg_quality, 1),
            "avg_complexity_score": round(avg_complexity, 1),
            "total_issues": total_issues,
        }


_analyzer_instance: CodeAnalyzer | None = None


def get_code_analyzer() -> CodeAnalyzer:
    global _analyzer_instance
    if _analyzer_instance is None:
        _analyzer_instance = CodeAnalyzer()
    return _analyzer_instance
