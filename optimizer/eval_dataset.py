"""Eval dataset for JARVIS prompt optimization.

Each test case has:
- goal: the user's request
- expected_tools: ordered list of tools the agent should call
- forbidden_tools: tools it should NOT call for this goal
- max_iterations: reasonable upper bound on loop iterations
- category: classification for error analysis
"""

EVAL_DATASET = [
    # ── Filesystem operations ──────────────────────────────────────────
    {
        "id": "fs_01",
        "goal": "List all Python files in the project",
        "expected_tools": ["search.find"],
        "forbidden_tools": ["shell.execute"],
        "max_iterations": 3,
        "category": "filesystem",
    },
    {
        "id": "fs_02",
        "goal": "Read the contents of requirements.txt",
        "expected_tools": ["filesystem.read"],
        "forbidden_tools": ["shell.execute"],
        "max_iterations": 2,
        "category": "filesystem",
    },
    {
        "id": "fs_03",
        "goal": "Create a new file called hello.py that prints 'Hello, World!'",
        "expected_tools": ["filesystem.write"],
        "forbidden_tools": ["shell.execute"],
        "max_iterations": 2,
        "category": "filesystem",
    },
    {
        "id": "fs_04",
        "goal": "Show me the git status of this repository",
        "expected_tools": ["git.status"],
        "forbidden_tools": ["shell.execute"],
        "max_iterations": 2,
        "category": "git",
    },
    {
        "id": "fs_05",
        "goal": "What are the last 5 commits in this repo?",
        "expected_tools": ["git.log"],
        "forbidden_tools": ["shell.execute"],
        "max_iterations": 2,
        "category": "git",
    },

    # ── Code editing ───────────────────────────────────────────────────
    {
        "id": "edit_01",
        "goal": "In main.py, change the print statement to say 'Hello, JARVIS' instead of 'Hello, World'",
        "expected_tools": ["filesystem.read", "patch.replace"],
        "forbidden_tools": ["filesystem.write"],
        "max_iterations": 4,
        "category": "editing",
    },
    {
        "id": "edit_02",
        "goal": "Add a new function calculate_average to utils.py that takes a list of numbers and returns the average",
        "expected_tools": ["filesystem.read", "patch.insert"],
        "forbidden_tools": ["filesystem.write"],
        "max_iterations": 4,
        "category": "editing",
    },
    {
        "id": "edit_03",
        "goal": "Remove the unused import 'os' from app.py",
        "expected_tools": ["filesystem.read", "patch.delete"],
        "forbidden_tools": ["filesystem.write"],
        "max_iterations": 4,
        "category": "editing",
    },

    # ── Code search ────────────────────────────────────────────────────
    {
        "id": "search_01",
        "goal": "Find all places where 'sqlite' is imported in this project",
        "expected_tools": ["search.code"],
        "forbidden_tools": ["shell.execute"],
        "max_iterations": 3,
        "category": "search",
    },
    {
        "id": "search_02",
        "goal": "Find the definition of the AgentLoop class",
        "expected_tools": ["search.code"],
        "forbidden_tools": ["shell.execute"],
        "max_iterations": 3,
        "category": "search",
    },

    # ── Multi-step tasks ───────────────────────────────────────────────
    {
        "id": "multi_01",
        "goal": "Check what's in the config/ directory and read the main config file",
        "expected_tools": ["filesystem.list", "filesystem.read"],
        "forbidden_tools": ["shell.execute"],
        "max_iterations": 4,
        "category": "multi_step",
    },
    {
        "id": "multi_02",
        "goal": "Show me the project structure and then read the README",
        "expected_tools": ["filesystem.list", "filesystem.read"],
        "forbidden_tools": ["shell.execute"],
        "max_iterations": 4,
        "category": "multi_step",
    },

    # ── System queries ─────────────────────────────────────────────────
    {
        "id": "sys_01",
        "goal": "What is the current CPU and memory usage?",
        "expected_tools": ["system.status"],
        "forbidden_tools": ["shell.execute"],
        "max_iterations": 2,
        "category": "system",
    },

    # ── Edge cases ─────────────────────────────────────────────────────
    {
        "id": "edge_01",
        "goal": "What is 2 + 2?",
        "expected_tools": [],
        "forbidden_tools": ["shell.execute", "filesystem.write"],
        "max_iterations": 1,
        "category": "no_tools",
    },
    {
        "id": "edge_02",
        "goal": "Tell me a joke",
        "expected_tools": [],
        "forbidden_tools": ["shell.execute", "filesystem.write"],
        "max_iterations": 1,
        "category": "no_tools",
    },

    # ── Inspect-before-act tests ───────────────────────────────────────
    {
        "id": "inspect_01",
        "goal": "Find where the ProviderRouter class is defined and show me its __init__ method",
        "expected_tools": ["search.code", "filesystem.read"],
        "forbidden_tools": ["shell.execute"],
        "max_iterations": 5,
        "category": "inspect_before_act",
    },
    {
        "id": "inspect_02",
        "goal": "List files in the tools/ directory, then read the registry.py file",
        "expected_tools": ["filesystem.list", "filesystem.read"],
        "forbidden_tools": ["shell.execute"],
        "max_iterations": 4,
        "category": "inspect_before_act",
    },

    # ── Git workflow ───────────────────────────────────────────────────
    {
        "id": "git_01",
        "goal": "Show me what files have changed and what the diff looks like",
        "expected_tools": ["git.status", "git.diff"],
        "forbidden_tools": ["shell.execute"],
        "max_iterations": 4,
        "category": "git",
    },
    {
        "id": "git_02",
        "goal": "What branch am I on and what's the recent commit history?",
        "expected_tools": ["git.branch", "git.log"],
        "forbidden_tools": ["shell.execute"],
        "max_iterations": 4,
        "category": "git",
    },

    # ── Behavioral tests ───────────────────────────────────────────────
    {
        "id": "behavior_01",
        "goal": "Read the entire codebase and summarize every file",
        "expected_tools": ["filesystem.list", "filesystem.read"],
        "forbidden_tools": ["shell.execute"],
        "max_iterations": 10,
        "category": "behavior",
    },
    {
        "id": "behavior_02",
        "goal": "Search for all TODO comments in the codebase",
        "expected_tools": ["search.code"],
        "forbidden_tools": ["shell.execute"],
        "max_iterations": 3,
        "category": "behavior",
    },
]


def get_dataset():
    """Return the full eval dataset."""
    return EVAL_DATASET


def get_categories():
    """Return unique categories in the dataset."""
    return sorted(set(item["category"] for item in EVAL_DATASET))


def get_by_category(category: str):
    """Return all items in a category."""
    return [item for item in EVAL_DATASET if item["category"] == category]
