---
name: repo_mine_tools
description: Turn items from the GitHub repo-mine list (docs/UI-REPO-DERIVED-ROADMAP.md) into new JARVIS agent tools following house conventions — lazy imports, root-safe writes, registry registration, hermetic tests, risk classification.
origin: JARVIS repo-mine pass 6 (data tools, doc.report, routines)
---

# Repo-Mine Tool Pass — build JARVIS tools from the GitHub repo list

## When to Use

- The user asks to "continue improving JARVIS from the repo list" / "go through
  the github repos and use what's useful"
- A roadmap item marked NEXT/LATER is being promoted into shipped tools
- Any new agent tool is being added, regardless of origin

## The Workflow

### 1. Pick the tranche (don't repeat shipped work)

- Read `docs/UI-REPO-DERIVED-ROADMAP.md` — every DONE item lists the tool
  names that satisfy it.
- `git log --oneline` + `ls tools/` to see what exists.
- Prefer items marked NEXT; each should map to a concrete tool name.

### 2. Check dependencies before choosing libraries

```bash
python -c "import importlib.util; print(bool(importlib.util.find_spec('X')))"
```

Only standard-library + already-installed deps ship unconditionally; add
optional deps to `requirements.txt` with a comment explaining what uses them.
Guard imports inside handlers and return a helpful ToolResult error when a
dep is missing ("X not installed (pip install X)") — never at module import.

### 3. Follow the handler contract

One module per family under `tools/`, mirroring `tools/pdf_tools.py`:

- Handlers are sync functions: `(args: dict) -> ToolResult`.
- Resolve paths via `ProjectContext.discover().root_path`; **absolutely
  require writes to resolve inside the project root** (the `_safe_dest`
  pattern). Reads may be absolute.
- Cap input sizes (`MAX_BYTES` before parsing) and output via
  `truncate(...)` from `tools.schema`.
- Top of file: provenance docstring naming the source repos.
- Model-friendly errors: on a bad query, include the column/param list so
  the model can self-correct on the next call.

**The boundary rule (P0 from the Orbit audit):** a tool handler must never
nest tool execution — no `build_default_registry()` lookups to *call* other
tools, no executor construction. If a tool's job is orchestration (e.g.
`routine.run`), validate against the registry and return an ordered **plan**
in `output`/`metadata`; the agent executes each step through the normal
ToolExecutionService path so every step is permission-checked and audited.

### 4. Register in `tools/__init__.py`

- Import handlers in the lazy import block (alphabetical grouping).
- Add a `Tool(...)` entry in the `classify_tool(t)` list: `name` uses a
  dotted namespace ("data.stats"), `description` is written for the model
  (when to use it, not what it is), `permission` follows the existing
  vocabulary (filesystem.read/write, web.search, system.status), `category`
  matches the namespace.

### 5. Classify risk in `tests/test_tool_inventory.py`

Every registered tool must be in READ_ONLY_TOOLS, MUTATING_TOOLS, or
DANGEROUS_TOOLS or the inventory test fails:

- Reads (analysis, listing, plan-returning run) → READ_ONLY
- Writes files under root / persists state → MUTATING
- Shell/browser mutations → DANGEROUS

### 6. Hermetic tests

New file `tests/test_repo_mine_pass<N>.py` (or extend the existing one):

- Monkeypatch the seam: `ProjectContext.discover` (patch the class, not the
  importing module — handlers import lazily inside the function body):

  ```python
  from core.project import ProjectContext
  monkeypatch.setattr(ProjectContext, "discover",
                      staticmethod(lambda cwd=None: type("C", (), {"root_path": tmp_path})()))
  ```

- Generate fixtures in `tmp_path` (CSVs with pandas, PDFs with pypdf, JSON
  inline). No network.
- Assert on `res.success`, `res.output` substrings, and `res.metadata`.
- For orchestration tools, assert the **negative**: no nested execution
  happened (monkeypatch the referenced handler with a canary and assert it
  never fired).
- Expect the unexpected: `level=0` docx headings use the "Title" style, not
  "Heading 0".

### 7. Close the loop

- Update the roadmap statuses (LATER/NEXT → DONE with tool names in
  parentheses) and add a "Shipped in pass N" section.
- Run the new tests + `tests/test_tool_inventory.py` +
  `tests/test_repo_mine_tools.py`.
- `python -m py_compile` every touched module.

## Good Examples in the Tree

- `tools/pdf_tools.py` — the canonical module layout
- `tools/routines.py` — the plan-not-execute orchestration pattern
- `tools/data_tools.py` — dependency-guarded imports + model-friendly errors
