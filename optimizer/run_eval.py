"""Local Prompt Optimizer for JARVIS MK-X.

Compares the current system prompt against an improved version using
the eval dataset. Uses the active ProviderRouter to test each prompt
against the LLM.

Usage:
    python optimizer/run_eval.py [--baseline] [--improved] [--compare]
"""

from __future__ import annotations

import asyncio
import json
import sys
import time

# Fix Windows console encoding for Unicode output
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
from dataclasses import dataclass, field
from pathlib import Path

# Add project root to path
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))

from optimizer.eval_dataset import get_dataset

# ── Prompt versions ────────────────────────────────────────────────────

CURRENT_PROMPT = """\
You are JARVIS MK-X, an autonomous engineering agent running on a Windows PC.

CRITICAL: For simple questions, greetings, opinions, math, jokes, or anything
that does NOT require reading/writing files or running commands, answer directly
in 1-3 sentences. Do NOT call tools for things you can answer from knowledge.
Examples of DIRECT answers (no tools needed):
  - 'hello' -> 'Hello! How can I help you today?'
  - 'what is 2+2' -> '4'
  - 'tell me a joke' -> tell a joke
  - 'what time is it' -> give the time

For tasks that require code changes, file operations, or system commands:

Methodology (follow this order):
1. UNDERSTAND: Parse the user's goal. Identify what information or changes are needed.
2. EXPLORE: Before making changes, read relevant files first.
3. PLAN: State your approach in 1-2 sentences before acting.
4. EXECUTE: Make precise, minimal changes.
5. VERIFY: After changes, confirm the result is correct.

Tool Selection Rules:
- Use filesystem.read to read file contents (NOT shell.execute with cat/type)
- Use filesystem.list to list directories (NOT shell.execute with dir/ls)
- Use search.code to search file contents (NOT shell.execute with grep)
- Use search.find to find files by name pattern (NOT shell.execute with find/where)
- Use git.status / git.diff / git.log for git operations (NOT shell.execute)
- Use patch.replace for editing existing files — provide exact old text and new text
- Use patch.insert to add code at a specific line
- Use patch.delete to remove lines from a file
- Use filesystem.write ONLY for creating new files
- Use shell.execute ONLY when no other tool can accomplish the task

Rules:
- Inspect before acting: always read a file before modifying it.
- Pass exact argument names shown in each tool's schema; never invent parameters.
- On a tool error, read it, adapt, and retry with a corrected call.
- Never fabricate tool results. Report what actually happened.
- If a tool is denied or fails, do NOT retry the same call — adapt or explain.
- Make minimal changes: edit only what needs to change, don't rewrite entire files.
- Stop as soon as the goal is complete and summarize what you did in 2-3 sentences.
- Do NOT call tools unless the task explicitly requires file/system operations."""

IMPROVED_PROMPT = """\
You are JARVIS MK-X, an autonomous engineering agent running on a Windows PC.
You accomplish the user's goal by calling tools. You may call tools repeatedly.

## Methodology (follow this order)
1. UNDERSTAND: Parse the user's goal. Identify what information or changes are needed.
2. EXPLORE: Before making changes, read relevant files. Use search.code to find definitions, search.find to locate files, filesystem.list to understand structure.
3. PLAN: State your approach in 1-2 sentences before acting.
4. EXECUTE: Make precise, minimal changes. Prefer patch.replace/insert/delete over rewriting entire files.
5. VERIFY: After changes, confirm the result is correct (re-read the file, run a check if appropriate).

## Tool Selection Rules
- Use filesystem.read to read file contents (NOT shell.execute with cat/type)
- Use filesystem.list to list directories (NOT shell.execute with dir/ls)
- Use search.code to search file contents (NOT shell.execute with grep)
- Use search.find to find files by name pattern (NOT shell.execute with find/where)
- Use git.status / git.diff / git.log for git operations (NOT shell.execute with git commands)
- Use patch.replace for editing existing files — provide exact old text and new text
- Use patch.insert to add code at a specific line
- Use patch.delete to remove lines from a file
- Use filesystem.write ONLY for creating new files
- Use shell.execute ONLY when no other tool can accomplish the task
- NEVER use shell.execute for tasks that filesystem, search, or git tools handle

## Rules
- Inspect before acting: always read a file before modifying it.
- Pass exact argument names shown in each tool's schema; never invent parameters.
- On a tool error, read it, adapt, and retry with a corrected call.
- Never fabricate tool results. Report what actually happened.
- If a tool is denied or fails, do NOT retry the same call — adapt or explain.
- Make minimal changes: edit only what needs to change, don't rewrite entire files.
- Stop as soon as the goal is complete and summarize what you did in 2-3 sentences.
- For simple questions (math, jokes, opinions), answer directly without calling tools."""


# ── Evaluation framework ──────────────────────────────────────────────

@dataclass
class EvalResult:
    """Result of evaluating a single test case."""
    test_id: str
    goal: str
    category: str
    tools_called: list[str] = field(default_factory=list)
    correct_tools: list[str] = field(default_factory=list)
    wrong_tools: list[str] = field(default_factory=list)
    forbidden_called: list[str] = field(default_factory=list)
    iterations: int = 0
    success: bool = False
    error: str = ""
    duration_ms: float = 0.0
    tokens_used: int = 0
    raw_response: str = ""

    @property
    def tool_accuracy(self) -> float:
        if not self.correct_tools and not self.wrong_tools:
            return 1.0  # no tools needed, none called = correct
        total = len(self.correct_tools) + len(self.wrong_tools)
        return len(self.correct_tools) / total if total > 0 else 0.0

    @property
    def penalty_score(self) -> float:
        """Penalize for calling forbidden tools or using too many iterations."""
        score = self.tool_accuracy
        if self.forbidden_called:
            score *= 0.5  # heavy penalty for using forbidden tools
        return score


@dataclass
class EvalReport:
    """Aggregate evaluation report."""
    results: list[EvalResult] = field(default_factory=list)
    prompt_version: str = ""
    total_duration_ms: float = 0.0

    @property
    def total(self) -> int:
        return len(self.results)

    @property
    def avg_tool_accuracy(self) -> float:
        if not self.results:
            return 0.0
        return sum(r.tool_accuracy for r in self.results) / len(self.results)

    @property
    def avg_penalty_score(self) -> float:
        if not self.results:
            return 0.0
        return sum(r.penalty_score for r in self.results) / len(self.results)

    @property
    def forbidden_violations(self) -> int:
        return sum(1 for r in self.results if r.forbidden_called)

    def by_category(self) -> dict[str, list[EvalResult]]:
        cats: dict[str, list[EvalResult]] = {}
        for r in self.results:
            cats.setdefault(r.category, []).append(r)
        return cats

    def summary(self) -> str:
        lines = [
            f"═══ Eval Report: {self.prompt_version} ═══",
            f"Total cases: {self.total}",
            f"Avg tool accuracy: {self.avg_tool_accuracy:.1%}",
            f"Avg penalty score: {self.avg_penalty_score:.1%}",
            f"Forbidden tool violations: {self.forbidden_violations}",
            f"Total duration: {self.total_duration_ms:.0f}ms",
            "",
            "By category:",
        ]
        for cat, results in self.by_category().items():
            acc = sum(r.tool_accuracy for r in results) / len(results)
            lines.append(f"  {cat}: {acc:.1%} ({len(results)} cases)")

        # Show failures
        failures = [r for r in self.results if r.penalty_score < 1.0]
        if failures:
            lines.append("")
            lines.append("Issues found:")
            for r in failures:
                lines.append(f"  [{r.test_id}] {r.goal[:60]}...")
                if r.forbidden_called:
                    lines.append(f"    FORBIDDEN tools called: {r.forbidden_called}")
                if r.wrong_tools:
                    lines.append(f"    Unexpected tools: {r.wrong_tools}")
                if r.error:
                    lines.append(f"    Error: {r.error[:100]}")

        return "\n".join(lines)


def parse_tool_calls_from_response(response: str) -> list[str]:
    """Extract tool call names from an LLM response.

    Only matches tool names in actual tool-call contexts (XML tags, JSON
    function calls, or explicit 'I will use X' statements), not random
    mentions in natural language.
    """
    import re

    KNOWN_TOOLS = {
        'filesystem.read', 'filesystem.write', 'filesystem.list',
        'shell.execute', 'system.status', 'web.search',
        'search.code', 'search.find',
        'git.status', 'git.diff', 'git.log', 'git.branch',
        'git.add', 'git.commit', 'git.restore',
        'patch.replace', 'patch.insert', 'patch.delete',
    }
    tools = []

    # Pattern 1: XML-style tool calls (most reliable)
    xml_pattern = re.compile(r'<([a-zA-Z_][a-zA-Z0-9_.]*)>\s*\{')
    for m in xml_pattern.finditer(response):
        name = m.group(1)
        if name in KNOWN_TOOLS:
            tools.append(name)

    # Pattern 2: JSON function call format
    func_pattern = re.compile(r'"function"\s*:\s*\{\s*"name"\s*:\s*"([^"]+)"')
    for m in func_pattern.finditer(response):
        name = m.group(1)
        if name in KNOWN_TOOLS:
            tools.append(name)

    # Pattern 3: Explicit tool usage statements ("I will use X", "calling X", "use X")
    use_pattern = re.compile(
        r'(?:I will use|calling|use|using|invoke|execute)\s+(' +
        r'|'.join(re.escape(t) for t in KNOWN_TOOLS) + r')',
        re.IGNORECASE
    )
    for m in use_pattern.finditer(response):
        tools.append(m.group(1))

    return list(dict.fromkeys(tools))  # deduplicate preserving order


async def eval_single(
    test_case: dict,
    router,
    system_prompt: str,
    max_tokens: int = 500,
) -> EvalResult:
    """Evaluate a single test case against the LLM."""
    from providers.types import LLMResponse

    result = EvalResult(
        test_id=test_case["id"],
        goal=test_case["goal"],
        category=test_case["category"],
    )

    messages = [{"role": "user", "content": test_case["goal"]}]

    start = time.perf_counter()
    try:
        response: LLMResponse = await router.complete(
            messages,
            system_prompt=system_prompt,
            max_tokens=max_tokens,
            temperature=0.1,
        )
        result.raw_response = response.text or ""
        result.tokens_used = response.tokens_used
        result.duration_ms = (time.perf_counter() - start) * 1000

        # Parse tool calls from response
        tools_called = parse_tool_calls_from_response(response.text or "")
        result.tools_called = tools_called

        # Score against expected
        expected = set(test_case.get("expected_tools", []))
        forbidden = set(test_case.get("forbidden_tools", []))

        result.correct_tools = [t for t in tools_called if t in expected]
        result.wrong_tools = [t for t in tools_called if t not in expected]
        result.forbidden_called = [t for t in tools_called if t in forbidden]

        # If no tools were expected and none were called, that's correct
        if not expected and not tools_called:
            result.correct_tools = []
            result.wrong_tools = []

        result.success = result.penalty_score >= 0.8
    except Exception as e:
        result.error = str(e)[:200]
        result.duration_ms = (time.perf_counter() - start) * 1000

    return result


async def run_evaluation(
    system_prompt: str,
    prompt_version: str = "baseline",
    dataset: list[dict] | None = None,
    max_concurrency: int = 1,
) -> EvalReport:
    """Run full evaluation with a given system prompt."""
    from core.config import Config
    from providers.router import ProviderRouter

    if dataset is None:
        dataset = get_dataset()

    config = Config.instance()
    router = ProviderRouter(config.get_section("models"), config.api_keys)

    report = EvalReport(prompt_version=prompt_version)
    start = time.perf_counter()

    print(f"\n{'='*60}")
    print(f"  Evaluating: {prompt_version}")
    print(f"  Test cases: {len(dataset)}")
    print(f"{'='*60}\n")

    for i, test_case in enumerate(dataset):
        print(f"  [{i+1}/{len(dataset)}] {test_case['id']}: {test_case['goal'][:50]}...", end=" ", flush=True)
        result = await eval_single(test_case, router, system_prompt)
        report.results.append(result)
        # Small delay to avoid Gemini rate limits
        await asyncio.sleep(1.5)

        status = "OK" if result.success else "FAIL"
        print(f"{status} ({result.duration_ms:.0f}ms)")

        if result.forbidden_called:
            print(f"         [!] Forbade: {result.forbidden_called}")
        if result.wrong_tools:
            print(f"         [!] Wrong: {result.wrong_tools}")

    report.total_duration_ms = (time.perf_counter() - start) * 1000
    print(f"\n{report.summary()}")
    return report


def compare_reports(baseline: EvalReport, improved: EvalReport) -> str:
    """Compare two eval reports and highlight improvements/regressions."""
    lines = [
        "═══ Comparison Report ═══",
        f"Baseline: {baseline.prompt_version}",
        f"Improved: {improved.prompt_version}",
        "",
        f"{'Metric':<30} {'Baseline':>12} {'Improved':>12} {'Delta':>10}",
        f"{'─'*30} {'─'*12} {'─'*12} {'─'*10}",
    ]

    metrics = [
        ("Avg Tool Accuracy", baseline.avg_tool_accuracy, improved.avg_tool_accuracy),
        ("Avg Penalty Score", baseline.avg_penalty_score, improved.avg_penalty_score),
        ("Forbidden Violations", baseline.forbidden_violations, improved.forbidden_violations),
    ]

    for name, base_val, imp_val in metrics:
        delta = imp_val - base_val
        if isinstance(base_val, int):
            lines.append(f"{name:<30} {base_val:>12} {imp_val:>12} {delta:>+10}")
        else:
            lines.append(f"{name:<30} {base_val:>11.1%} {imp_val:>11.1%} {delta:>+9.1%}")

    # Per-category comparison
    base_cats = baseline.by_category()
    imp_cats = improved.by_category()
    all_cats = sorted(set(list(base_cats.keys()) + list(imp_cats.keys())))

    lines.append("")
    lines.append("By category:")
    lines.append(f"  {'Category':<20} {'Baseline':>12} {'Improved':>12} {'Delta':>10}")
    lines.append(f"  {'─'*20} {'─'*12} {'─'*12} {'─'*10}")

    for cat in all_cats:
        base_results = base_cats.get(cat, [])
        imp_results = imp_cats.get(cat, [])
        base_acc = sum(r.tool_accuracy for r in base_results) / len(base_results) if base_results else 0
        imp_acc = sum(r.tool_accuracy for r in imp_results) / len(imp_results) if imp_results else 0
        delta = imp_acc - base_acc
        lines.append(f"  {cat:<20} {base_acc:>11.1%} {imp_acc:>11.1%} {delta:>+9.1%}")

    # Individual case improvements/regressions
    base_map = {r.test_id: r for r in baseline.results}
    imp_map = {r.test_id: r for r in improved.results}

    improvements = []
    regressions = []
    for tid in base_map:
        if tid in imp_map:
            b = base_map[tid]
            i = imp_map[tid]
            if i.penalty_score > b.penalty_score:
                improvements.append((tid, b, i))
            elif i.penalty_score < b.penalty_score:
                regressions.append((tid, b, i))

    if improvements:
        lines.append("")
        lines.append(f"Improvements ({len(improvements)}):")
        for tid, b, i in improvements:
            lines.append(f"  [{tid}] {b.goal[:50]}... ({b.penalty_score:.0%} → {i.penalty_score:.0%})")

    if regressions:
        lines.append("")
        lines.append(f"Regressions ({len(regressions)}):")
        for tid, b, i in regressions:
            lines.append(f"  [{tid}] {b.goal[:50]}... ({b.penalty_score:.0%} → {i.penalty_score:.0%})")

    return "\n".join(lines)


def main():
    import argparse

    parser = argparse.ArgumentParser(description="JARVIS Prompt Optimizer")
    parser.add_argument("--baseline", action="store_true", help="Run baseline evaluation only")
    parser.add_argument("--improved", action="store_true", help="Run improved evaluation only")
    parser.add_argument("--compare", action="store_true", help="Run both and compare")
    args = parser.parse_args()

    if not any([args.baseline, args.improved, args.compare]):
        args.compare = True

    async def _run():
        if args.baseline or args.compare:
            baseline = await run_evaluation(CURRENT_PROMPT, "baseline")
            # Save results
            Path("optimizer/results").mkdir(exist_ok=True)
            with open("optimizer/results/baseline.json", "w") as f:
                json.dump({
                    "prompt_version": baseline.prompt_version,
                    "avg_tool_accuracy": baseline.avg_tool_accuracy,
                    "avg_penalty_score": baseline.avg_penalty_score,
                    "forbidden_violations": baseline.forbidden_violations,
                    "total_duration_ms": baseline.total_duration_ms,
                    "results": [
                        {
                            "id": r.test_id,
                            "goal": r.goal,
                            "category": r.category,
                            "tools_called": r.tools_called,
                            "correct_tools": r.correct_tools,
                            "wrong_tools": r.wrong_tools,
                            "forbidden_called": r.forbidden_called,
                            "penalty_score": r.penalty_score,
                            "error": r.error,
                            "duration_ms": r.duration_ms,
                        }
                        for r in baseline.results
                    ],
                }, f, indent=2)

        if args.improved or args.compare:
            improved = await run_evaluation(IMPROVED_PROMPT, "improved")
            Path("optimizer/results").mkdir(exist_ok=True)
            with open("optimizer/results/improved.json", "w") as f:
                json.dump({
                    "prompt_version": improved.prompt_version,
                    "avg_tool_accuracy": improved.avg_tool_accuracy,
                    "avg_penalty_score": improved.avg_penalty_score,
                    "forbidden_violations": improved.forbidden_violations,
                    "total_duration_ms": improved.total_duration_ms,
                    "results": [
                        {
                            "id": r.test_id,
                            "goal": r.goal,
                            "category": r.category,
                            "tools_called": r.tools_called,
                            "correct_tools": r.correct_tools,
                            "wrong_tools": r.wrong_tools,
                            "forbidden_called": r.forbidden_called,
                            "penalty_score": r.penalty_score,
                            "error": r.error,
                            "duration_ms": r.duration_ms,
                        }
                        for r in improved.results
                    ],
                }, f, indent=2)

        if args.compare:
            print("\n\n" + compare_reports(baseline, improved))

    asyncio.run(_run())


if __name__ == "__main__":
    main()
