"""Code Generator — Generate code from natural language descriptions.

Uses LLM to translate natural language specifications into executable code.
"""
import logging
import json
import re
import time
from typing import Optional, Dict, Any, List
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger("se_factory.code_generator")


@dataclass
class CodeRequest:
    """Request for code generation."""
    description: str
    language: str = "python"
    style: str = "standard"  # standard, functional, oop
    include_tests: bool = False
    include_docstrings: bool = True
    max_lines: int = 200


@dataclass
class CodeResult:
    """Result of code generation."""
    code: str
    language: str
    explanation: str = ""
    files: Dict[str, str] = field(default_factory=dict)
    generation_ms: float = 0.0
    success: bool = True
    error: str = ""


class CodeGenerator:
    """Generates code from natural language descriptions using LLM."""

    def __init__(self, llm_fn=None):
        """
        Args:
            llm_fn: Async function(prompt: str) -> str that calls an LLM.
                    If None, uses a template-based fallback.
        """
        self._llm_fn = llm_fn
        self._history: List[Dict[str, Any]] = []
        self._templates = self._load_templates()

    def _load_templates(self) -> Dict[str, str]:
        return {
            "function": 'def {name}({params}):\n    """{docstring}"""\n    {body}\n',
            "class": 'class {name}:\n    """{docstring}"""\n\n    def __init__(self{params}):\n{init_body}\n\n{methods}',
            "flask_route": '@app.route("/{endpoint}", methods=[{methods}])\ndef {name}():\n    """{docstring}"""\n    {body}\n',
            "test": 'def test_{name}():\n    """Test {description}"""\n    {body}\n',
        }

    async def generate(self, request: CodeRequest) -> CodeResult:
        """Generate code from a natural language description."""
        start = time.time()

        if self._llm_fn:
            result = await self._generate_with_llm(request)
        else:
            result = self._generate_with_template(request)

        result.generation_ms = (time.time() - start) * 1000

        self._history.append({
            "description": request.description[:100],
            "language": request.language,
            "success": result.success,
            "ms": result.generation_ms,
        })

        return result

    async def _generate_with_llm(self, request: CodeRequest) -> CodeResult:
        """Generate code using an LLM."""
        prompt = self._build_prompt(request)
        try:
            response = await self._llm_fn(prompt)
            code = self._extract_code(response)
            explanation = self._extract_explanation(response)
            return CodeResult(
                code=code,
                language=request.language,
                explanation=explanation,
                success=True,
            )
        except Exception as e:
            logger.error("LLM code generation failed: %s", e)
            return CodeResult(code="", language=request.language, success=False, error=str(e))

    def _build_prompt(self, request: CodeRequest) -> str:
        parts = [
            f"Generate {request.language} code for the following:",
            f"\n{request.description}\n",
            f"Style: {request.style}",
            f"Max lines: {request.max_lines}",
        ]
        if request.include_docstrings:
            parts.append("Include docstrings.")
        if request.include_tests:
            parts.append("Include unit tests.")
        parts.append("Return the code in a markdown code block.")
        return "\n".join(parts)

    def _extract_code(self, response: str) -> str:
        match = re.search(r'```(?:\w+)?\n(.*?)```', response, re.DOTALL)
        if match:
            return match.group(1).strip()
        return response.strip()

    def _extract_explanation(self, response: str) -> str:
        parts = response.split("```")
        if len(parts) > 1:
            before = parts[0].strip()
            if before:
                return before
        return ""

    def _generate_with_template(self, request: CodeRequest) -> CodeResult:
        """Template-based fallback when no LLM is available."""
        desc = request.description.lower()

        if "class" in desc or "object" in desc:
            name = self._extract_name(request.description)
            code = self._templates["class"].format(
                name=name, docstring=request.description,
                params="", init_body="        pass", methods=""
            )
        elif "test" in desc:
            name = self._extract_name(request.description)
            code = self._templates["test"].format(
                name=name, description=request.description,
                body="    pass"
            )
        else:
            name = self._extract_name(request.description)
            code = self._templates["function"].format(
                name=name, params="", docstring=request.description,
                body="    pass"
            )

        return CodeResult(code=code, language=request.language, success=True)

    def _extract_name(self, description: str) -> str:
        words = re.findall(r'[a-zA-Z_]+', description)
        if words:
            name = words[0].lower()
            if len(words) > 1:
                name = words[0].lower() + "".join(w.capitalize() for w in words[1:])
            return name
        return "generated_function"

    def get_history(self) -> List[Dict[str, Any]]:
        return list(self._history)

    def get_stats(self) -> Dict[str, Any]:
        total = len(self._history)
        successful = sum(1 for h in self._history if h["success"])
        avg_ms = sum(h["ms"] for h in self._history) / max(total, 1)
        return {
            "total_generations": total,
            "successful": successful,
            "failed": total - successful,
            "avg_generation_ms": round(avg_ms, 1),
        }


_generator_instance: Optional[CodeGenerator] = None


def get_code_generator(llm_fn=None) -> CodeGenerator:
    global _generator_instance
    if _generator_instance is None:
        _generator_instance = CodeGenerator(llm_fn=llm_fn)
    return _generator_instance
