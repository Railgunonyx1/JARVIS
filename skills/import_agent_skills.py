"""Import Agent Skills (``~/.agents/skills/*/SKILL.md``) into JARVIS.

JARVIS's skill stack is manifest-driven (``skills/manifests/*.json`` ->
``skills.registry``), while the desktop harness ships independent
``SKILL.md`` Agent Skills (prompt-optimizer, minimalist-ui, optimize, ...).
This importer unifies them: every Agent Skill becomes a first-class JARVIS
skill so ``skills.list`` / ``skills.load`` and the system-prompt skill block
advertise the same catalog the harness uses.

Per skill directory with a SKILL.md:

1. Parse YAML frontmatter (``name``, ``description``; falls back to the
   directory name / first paragraph).
2. Write ``skills/instructions/agent/<name>.md`` — the SKILL.md verbatim,
   with sibling ``*.md`` reference files appended as appendices so the
   instructions file is self-contained (progressive disclosure loads one
   file, not a tree). Test fixtures (``test-*.md``, ``*-LOG.md``) are
   excluded.
3. Write ``skills/manifests/agent_<name>.json`` with a curated tool list
   drawn from the live ``tools.build_default_registry`` catalog (phantom
   tool references are dropped, never emitted), risk, and tags.

Idempotent: existing manifests (hand-written or previously imported) are
left untouched unless ``--overwrite``. ``--dry-run`` prints the plan.

Usage::

    python skills/import_agent_skills.py [--dry-run] [--overwrite]
                                         [--src PATH]
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

DEFAULT_SRC = Path.home() / ".agents" / "skills"
MANIFESTS_DIR = PROJECT_ROOT / "skills" / "manifests"
INSTRUCTIONS_DIR = PROJECT_ROOT / "skills" / "instructions" / "agent"

# Reference-file hygiene: skill-development fixtures are not instructions.
_EXCLUDE_FILES = re.compile(r"(^test-|-LOG\.md$)", re.IGNORECASE)

# Frontmatter fence, e.g. "---\nname: x\ndescription: >-\n  ...\n---"
_FM = re.compile(r"\A---\s*\r?\n(.*?)\r?\n---\s*\r?\n?", re.DOTALL)


def norm(name: str) -> str:
    """Folder/skill name -> manifest key (same convention as existing manifests)."""
    return re.sub(r"[^a-z0-9]+", "_", name.strip().lower()).strip("_")


# Curated mappings from the LIVE tool catalog (tools.build_default_registry).
# Advisory skills map to [] — they shape behaviour, not tool calls.
# NOTE: agent_browser stays read-only here; acting skills (click/type) are
# gated by the browser_automation skill + permission system.
_TOOL_MAP: dict[str, dict[str, object]] = {
    "agent-browser": {
        "tools": ["browser.open", "browser.read", "browser.extract",
                  "browser.find", "browser.screenshot", "browser.status",
                  "browser.tabs", "browser.new_tab", "browser.switch_tab",
                  "browser.close_tab", "browser.scroll", "browser.wait"],
        "risk": "medium", "tags": ["browser", "automation", "research"],
    },
    "brainstorming": {"tools": [], "risk": "low", "tags": ["planning", "ideation"]},
    "convex-performance-audit": {"tools": [], "risk": "low", "tags": ["performance", "audit"]},
    "documentation-writer": {
        "tools": ["filesystem.read", "filesystem.write", "search.code", "docs.to_markdown"],
        "risk": "low", "tags": ["docs", "writing"],
    },
    "excalidraw-diagram-generator": {
        "tools": ["filesystem.read", "filesystem.write"],
        "risk": "low", "tags": ["diagrams", "docs"],
    },
    "executing-plans": {"tools": [], "risk": "low", "tags": ["planning", "execution"]},
    "f1-test-drive": {
        "tools": ["shell.execute", "test.run", "test.run_target", "runtime.status"],
        "risk": "medium", "tags": ["testing", "e2e", "f1"],
    },
    "find-skills": {
        "tools": ["skills.list", "skills.load"],
        "risk": "low", "tags": ["meta", "discovery"],
    },
    "improve-codebase-architecture": {
        "tools": ["search.code", "code.ast", "code.references", "code.imports",
                  "code.definition", "filesystem.read"],
        "risk": "low", "tags": ["architecture", "refactoring", "review"],
    },
    "industrial-brutalist-ui": {
        "tools": ["filesystem.write", "filesystem.read"],
        "risk": "low", "tags": ["ui", "design"],
    },
    "minimalist-ui": {
        "tools": ["filesystem.write", "filesystem.read"],
        "risk": "low", "tags": ["ui", "design", "frontend"],
    },
    "optimize": {"tools": [], "risk": "low", "tags": ["performance", "frontend"]},
    "performance": {"tools": [], "risk": "low", "tags": ["performance"]},
    "performance-optimization": {"tools": [], "risk": "low", "tags": ["performance"]},
    "planning-with-files": {
        "tools": ["filesystem.read", "filesystem.write"],
        "risk": "low", "tags": ["planning", "workflow"],
    },
    "prompt-optimizer": {"tools": [], "risk": "low", "tags": ["prompting", "advisory"]},
    "security-review": {
        "tools": ["security.scan_code", "security.scan_secrets",
                  "security.check_permissions"],
        "risk": "medium", "tags": ["security", "review"],
    },
    "shadcn-ui": {
        "tools": ["filesystem.read", "search.code"],
        "risk": "low", "tags": ["ui", "react", "frontend"],
    },
    "systematic-debugging": {"tools": [], "risk": "low", "tags": ["debugging", "methodology"]},
    "ui-ux-pro-max": {
        "tools": ["filesystem.write", "filesystem.read"],
        "risk": "low", "tags": ["ui", "ux", "design"],
    },
    "vercel-react-best-practices": {"tools": [], "risk": "low", "tags": ["react", "frontend"]},
    "vercel-react-native-skills": {"tools": [], "risk": "low", "tags": ["react-native", "mobile"]},
    "vercel-react-view-transitions": {"tools": [], "risk": "low", "tags": ["react", "frontend"]},
    "verification-before-completion": {
        "tools": ["test.run", "test.run_target", "test.failed"],
        "risk": "low", "tags": ["testing", "verification"],
    },
    "writing-plans": {
        "tools": ["filesystem.write", "filesystem.read"],
        "risk": "low", "tags": ["planning", "docs"],
    },
}

DEFAULT_ENTRY = {"tools": [], "risk": "low", "tags": []}


def parse_frontmatter(text: str) -> tuple[dict[str, str], str]:
    """Return ({name, description,...}, body) tolerating missing frontmatter."""
    m = _FM.match(text)
    if not m:
        return {}, text
    raw = m.group(1)
    body = text[m.end():]
    meta: dict[str, str] = {}
    try:
        import yaml  # optional at runtime; repo already depends on it
        data = yaml.safe_load(raw)
        if isinstance(data, dict):
            meta = {str(k): str(v).strip() for k, v in data.items() if v is not None}
    except Exception:
        pass
    if "description" not in meta:
        # fallback: first non-empty, non-heading paragraph line
        for line in body.splitlines():
            s = line.strip()
            if s and not s.startswith("#"):
                meta["description"] = s
                break
    return meta, body


def build_instructions_md(skill_dir: Path) -> str | None:
    """SKILL.md + sibling reference docs concatenated (self-contained)."""
    main = skill_dir / "SKILL.md"
    if not main.is_file():
        return None
    try:
        parts = [main.read_text(encoding="utf-8", errors="replace").replace("\r\n", "\n")]
        for aux in sorted(skill_dir.glob("*.md")):
            if aux.name.upper() == "SKILL.MD" or _EXCLUDE_FILES.search(aux.name):
                continue
            content = aux.read_text(encoding="utf-8", errors="replace").replace("\r\n", "\n")
            parts.append(f"\n\n---\n\n# Appendix: {aux.name}\n\n{content}")
        return "".join(parts)
    except OSError:
        return None


def live_tool_names() -> set[str]:
    try:
        from tools import build_default_registry
        return set(build_default_registry()._tools.keys())  # noqa: SLF001
    except Exception:
        return set()


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--src", type=Path, default=DEFAULT_SRC)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--overwrite", action="store_true",
                    help="replace existing manifests/instructions for these skills")
    args = ap.parse_args(argv)

    if not args.src.is_dir():
        print(f"source not found: {args.src}")
        return 1

    valid_tools = live_tool_names()
    manifests: dict[str, Path] = {}
    if MANIFESTS_DIR.is_dir():
        for p in MANIFESTS_DIR.glob("*.json"):
            manifests[p.name] = p

    # Existing DECLARED names (any file) — the registry dedupes by the
    # manifest's "name" field, not the filename, so this is the real key.
    declared: set[str] = set()
    for p in manifests.values():
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            if isinstance(data, dict) and data.get("name"):
                declared.add(str(data["name"]))
        except (OSError, json.JSONDecodeError):
            continue

    imported: list[str] = []
    skipped: list[str] = []
    failures: list[str] = []

    for skill_dir in sorted(args.src.iterdir()):
        if not skill_dir.is_dir():
            continue
        md = build_instructions_md(skill_dir)
        if md is None:
            continue
        meta, _body = parse_frontmatter(md)
        name = meta.get("name") or skill_dir.name
        key = norm(name)
        desc = " ".join((meta.get("description") or "").split()) or f"Imported skill: {name}"
        entry = _TOOL_MAP.get(name) or _TOOL_MAP.get(skill_dir.name) or DEFAULT_ENTRY

        manifest_name = f"agent_{key}.json"
        instructions_path = f"skills/instructions/agent/{key}.md"
        # Dedupe by declared name (native packs, soc packs, prior imports):
        # a second manifest with the same "name" would be dropped by the
        # registry with a warning, so never emit one.
        if (key in declared or manifest_name in manifests) and not args.overwrite:
            skipped.append(f"{name} (existing: {key})")
            continue

        # Never emit phantom tool references.
        tools = [t for t in entry["tools"] if not valid_tools or t in valid_tools]
        manifest = {
            "name": key,
            "description": desc,
            "tools": tools,
            "tags": list(entry["tags"]) + ["imported"],
            "risk": entry["risk"],
            "timeout": 120 if tools else 90,
            "version": "1.0.0",
            "instructions": instructions_path,
            "source": str(skill_dir),
        }
        if args.dry_run:
            imported.append(f"{name} -> {manifest_name} ({len(tools)} tools)")
            continue
        try:
            INSTRUCTIONS_DIR.mkdir(parents=True, exist_ok=True)
            (INSTRUCTIONS_DIR / f"{key}.md").write_text(md, encoding="utf-8")
            (MANIFESTS_DIR / manifest_name).write_text(
                json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
            imported.append(f"{name} -> {manifest_name} ({len(tools)} tools)")
        except OSError as e:
            failures.append(f"{name}: {e}")

    print(f"imported: {len(imported)}{'' if args.dry_run else ''}")
    for line in imported:
        print(f"  + {line}")
    if skipped:
        print(f"skipped (already exist; use --overwrite to replace): {len(skipped)}")
        for s in skipped:
            print(f"  = {s}")
    if failures:
        print(f"FAILED: {len(failures)}")
        for f in failures:
            print(f"  ! {f}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
