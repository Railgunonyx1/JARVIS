import json
import logging
import os
import re
import sqlite3
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

logger = logging.getLogger("jarvis.workflows.decomposer")

API_CONFIG_PATH = Path.home() / ".jarvis" / "config" / "api_keys.json"

_DECOMPOSE_MODEL = "gemini-2.5-flash"


def _decompose_model() -> str:
    """Read decompose model from config/models.toml [executor] section."""
    try:
        from core.config import Config
        return Config.instance().get("models", "executor.decompose_model", _DECOMPOSE_MODEL)
    except Exception:
        return _DECOMPOSE_MODEL


def _get_api_key() -> str:
    try:
        from core.config import Config
        key = Config.instance().api_keys.get("gemini", "")
        if key:
            return key
    except Exception:
        pass
    if os.environ.get("GEMINI_API_KEY"):
        return os.environ["GEMINI_API_KEY"]
    if API_CONFIG_PATH.exists():
        try:
            with open(API_CONFIG_PATH, encoding="utf-8") as f:
                return json.load(f).get("gemini_api_key", "")
        except Exception:
            pass
    return ""


class GoalType(Enum):
    RESEARCH    = "research"
    CREATION    = "creation"
    SYSTEM      = "system"
    FILE        = "file"
    WEB         = "web"
    MULTISTEP   = "multistep"
    UNKNOWN     = "unknown"


PATTERN_MAP: dict[str, list[dict]] = {
    "research": {
        "keywords": ["research", "find", "search", "look up", "investigate", "study", "analyze"],
        "sub_goals": [
            {"name": "search_information", "action": "web_search", "params_key": "query"},
            {"name": "compile_findings", "action": "file_controller", "params_key": "content"},
        ],
    },
    "file_create": {
        "keywords": ["create file", "write file", "save", "create a document", "make a file"],
        "sub_goals": [
            {"name": "prepare_content", "action": "generated_code", "params_key": "description"},
            {"name": "write_file", "action": "file_controller", "params_key": "content"},
        ],
    },
    "app_launch": {
        "keywords": ["open app", "launch", "start program", "open program"],
        "sub_goals": [
            {"name": "launch_application", "action": "open_app", "params_key": "app_name"},
        ],
    },
    "system_info": {
        "keywords": ["disk space", "system info", "processes", "running", "memory usage", "cpu"],
        "sub_goals": [
            {"name": "gather_info", "action": "system", "params_key": "action"},
        ],
    },
    "web_browse": {
        "keywords": ["open website", "browse", "go to", "visit site", "open youtube"],
        "sub_goals": [
            {"name": "open_site", "action": "browser", "params_key": "url"},
        ],
    },
    "code_generate": {
        "keywords": ["write code", "create program", "build app", "generate code", "make a script", "write a python"],
        "sub_goals": [
            {"name": "generate_code", "action": "generated_code", "params_key": "description"},
        ],
    },
    "clean_up": {
        "keywords": ["clean", "clear", "remove", "delete", "purge", "wipe"],
        "sub_goals": [
            {"name": "perform_cleanup", "action": "disk", "params_key": "action"},
        ],
    },
}


@dataclass
class SubGoal:
    id:          str   = field(default_factory=lambda: str(uuid.uuid4())[:8])
    name:        str   = ""
    action:      str   = ""
    params:      dict  = field(default_factory=dict)
    priority:    int   = 2
    depends_on:  list  = field(default_factory=list)
    deadline:    float = 0.0
    status:      str   = "pending"


class GoalDecomposer:

    def __init__(self, db_path: str | None = None):
        self._db_path = db_path or str(Path.home() / ".jarvis" / "workflows.db")
        self._lock = __import__("threading").Lock()
        self._init_db()

    def _init_db(self) -> None:
        try:
            conn = sqlite3.connect(self._db_path, timeout=5)
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("""
                CREATE TABLE IF NOT EXISTS goals (
                    id          TEXT PRIMARY KEY,
                    description TEXT NOT NULL,
                    goal_type   TEXT DEFAULT 'unknown',
                    priority    INTEGER DEFAULT 2,
                    status      TEXT DEFAULT 'pending',
                    deadline    REAL DEFAULT 0,
                    created_at  REAL NOT NULL,
                    updated_at  REAL NOT NULL,
                    raw_text    TEXT DEFAULT '',
                    metadata    TEXT DEFAULT '{}'
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS sub_goals (
                    id          TEXT PRIMARY KEY,
                    goal_id     TEXT NOT NULL,
                    name        TEXT NOT NULL,
                    action      TEXT NOT NULL,
                    params      TEXT DEFAULT '{}',
                    priority    INTEGER DEFAULT 2,
                    depends_on  TEXT DEFAULT '[]',
                    deadline    REAL DEFAULT 0,
                    status      TEXT DEFAULT 'pending',
                    created_at  REAL NOT NULL,
                    FOREIGN KEY (goal_id) REFERENCES goals(id) ON DELETE CASCADE
                )
            """)
            conn.commit()
            conn.close()
        except Exception as e:
            logger.error("Failed to init goal DB: %s", e)

    def classify_goal(self, text: str) -> GoalType:
        lower = text.lower()
        best_match: GoalType | None = None
        best_score = 0

        for goal_type, pattern in PATTERN_MAP.items():
            score = sum(1 for kw in pattern["keywords"] if kw in lower)
            if score > best_score:
                best_score = score
                type_map = {
                    "research": GoalType.RESEARCH,
                    "file_create": GoalType.FILE,
                    "app_launch": GoalType.SYSTEM,
                    "system_info": GoalType.SYSTEM,
                    "web_browse": GoalType.WEB,
                    "code_generate": GoalType.CREATION,
                    "clean_up": GoalType.SYSTEM,
                }
                best_match = type_map.get(goal_type, GoalType.UNKNOWN)

        if best_match and best_score >= 1:
            return best_match

        words = lower.split()
        if len(words) > 8:
            return GoalType.MULTISTEP

        return GoalType.UNKNOWN

    def decompose_pattern(self, text: str, goal_type: GoalType) -> list[SubGoal]:
        type_key = goal_type.value.lower()
        pattern = PATTERN_MAP.get(type_key)

        if not pattern:
            for key, val in PATTERN_MAP.items():
                lower = text.lower()
                if any(kw in lower for kw in val["keywords"]):
                    pattern = val
                    break

        if not pattern:
            return []

        sub_goals = []
        for i, sg_def in enumerate(pattern["sub_goals"]):
            sg = SubGoal(
                name=sg_def["name"],
                action=sg_def["action"],
                params={sg_def["params_key"]: text},
                priority=1 if i == 0 else 2,
                depends_on=[sub_goals[i - 1].id] if i > 0 else [],
            )
            sub_goals.append(sg)

        return sub_goals

    def decompose_llm(self, text: str) -> list[SubGoal]:
        api_key = _get_api_key()
        if not api_key:
            logger.warning("No API key for LLM decomposition, falling back to pattern")
            return []

        try:
            import google.generativeai as genai
            genai.configure(api_key=api_key)
            model = genai.GenerativeModel(
                model_name=_decompose_model(),
                system_instruction=(
                    "You decompose complex goals into sub-goals for an autonomous workflow engine.\n"
                    "Available actions: web_search, file_controller, generated_code, open_app, browser, "
                    "system, process_manager, shell, screen_analyzer, computer_control\n\n"
                    "Return ONLY valid JSON array of sub-goals:\n"
                    "[\n"
                    "  {\n"
                    '    "name": "short_name",\n'
                    '    "action": "action_name",\n'
                    '    "params": {"key": "value"},\n'
                    '    "priority": 1,\n'
                    '    "depends_on": []\n'
                    "  }\n"
                    "]\n\n"
                    "Rules:\n"
                    "- Max 6 sub-goals\n"
                    "- Set depends_on to reference names of sub-goals that must complete first\n"
                    "- priority: 1=highest, 3=lowest"
                ),
            )

            response = model.generate_content(f"Decompose this goal into sub-goals:\n\n{text}")
            raw = response.text.strip()
            raw = re.sub(r"```(?:json)?", "", raw).strip().rstrip("`").strip()

            parsed = json.loads(raw)
            if not isinstance(parsed, list):
                return []

            sub_goals = []
            name_to_id: dict[str, str] = {}
            for item in parsed:
                sg = SubGoal(
                    name=item.get("name", "step"),
                    action=item.get("action", "generated_code"),
                    params=item.get("params", {}),
                    priority=item.get("priority", 2),
                    depends_on=[],
                )
                name_to_id[sg.name] = sg.id
                sub_goals.append(sg)

            for sg, item in zip(sub_goals, parsed):
                dep_names = item.get("depends_on", [])
                sg.depends_on = [name_to_id[n] for n in dep_names if n in name_to_id]

            return sub_goals

        except Exception as e:
            logger.error("LLM decomposition failed: %s", e)
            return []

    def decompose(self, text: str) -> tuple[GoalType, list[SubGoal]]:
        goal_type = self.classify_goal(text)

        if goal_type == GoalType.UNKNOWN:
            sub_goals = self.decompose_llm(text)
            if sub_goals:
                return goal_type, sub_goals

        sub_goals = self.decompose_pattern(text, goal_type)

        if not sub_goals and goal_type != GoalType.UNKNOWN:
            sub_goals = self.decompose_llm(text)

        return goal_type, sub_goals

    def save_goal(self, goal_id: str, description: str, goal_type: GoalType,
                  priority: int = 2, deadline: float = 0.0,
                  sub_goals: list[SubGoal] | None = None, metadata: dict | None = None) -> None:
        now = time.time()
        try:
            conn = sqlite3.connect(self._db_path, timeout=5)
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("""
                INSERT OR REPLACE INTO goals
                (id, description, goal_type, priority, status, deadline, created_at, updated_at, raw_text, metadata)
                VALUES (?, ?, ?, ?, 'pending', ?, ?, ?, ?, ?)
            """, (goal_id, description, goal_type.value, priority, deadline, now, now,
                  description, json.dumps(metadata or {})))

            if sub_goals:
                conn.execute("DELETE FROM sub_goals WHERE goal_id = ?", (goal_id,))
                for sg in sub_goals:
                    conn.execute("""
                        INSERT INTO sub_goals
                        (id, goal_id, name, action, params, priority, depends_on, deadline, status, created_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?)
                    """, (sg.id, goal_id, sg.name, sg.action, json.dumps(sg.params),
                          sg.priority, json.dumps(sg.depends_on), sg.deadline, now))

            conn.commit()
            conn.close()
        except Exception as e:
            logger.error("Failed to save goal: %s", e)

    def load_goal(self, goal_id: str) -> dict | None:
        try:
            conn = sqlite3.connect(self._db_path, timeout=5)
            conn.row_factory = sqlite3.Row
            row = conn.execute("SELECT * FROM goals WHERE id = ?", (goal_id,)).fetchone()
            if not row:
                conn.close()
                return None

            goal = dict(row)

            sub_rows = conn.execute(
                "SELECT * FROM sub_goals WHERE goal_id = ? ORDER BY created_at", (goal_id,)
            ).fetchall()
            goal["sub_goals"] = [dict(r) for r in sub_rows]

            conn.close()
            return goal
        except Exception as e:
            logger.error("Failed to load goal: %s", e)
            return None

    def update_sub_goal_status(self, sub_goal_id: str, status: str) -> bool:
        try:
            conn = sqlite3.connect(self._db_path, timeout=5)
            conn.execute("UPDATE sub_goals SET status = ? WHERE id = ?", (status, sub_goal_id))
            conn.commit()
            changed = conn.total_changes > 0
            conn.close()
            return changed
        except Exception as e:
            logger.error("Failed to update sub-goal status: %s", e)
            return False

    def get_dependency_graph(self, sub_goals: list[SubGoal]) -> dict[str, list[str]]:
        graph: dict[str, list[str]] = {sg.id: [] for sg in sub_goals}
        id_map = {sg.id: sg for sg in sub_goals}

        for sg in sub_goals:
            for dep_id in sg.depends_on:
                if dep_id in graph:
                    graph[dep_id].append(sg.id)

        return graph

    def topological_sort(self, sub_goals: list[SubGoal]) -> list[SubGoal]:
        if not sub_goals:
            return []

        id_map = {sg.id: sg for sg in sub_goals}
        in_degree: dict[str, int] = {sg.id: 0 for sg in sub_goals}

        for sg in sub_goals:
            for dep_id in sg.depends_on:
                if dep_id in in_degree:
                    in_degree[sg.id] += 1

        queue = [sid for sid, deg in in_degree.items() if deg == 0]
        result: list[SubGoal] = []

        while queue:
            queue.sort(key=lambda sid: id_map[sid].priority)
            node = queue.pop(0)
            result.append(id_map[node])

            for sg in sub_goals:
                if node in sg.depends_on:
                    in_degree[sg.id] -= 1
                    if in_degree[sg.id] == 0:
                        queue.append(sg.id)

        if len(result) != len(sub_goals):
            logger.warning("Circular dependency detected, appending remaining sub-goals")
            seen = {sg.id for sg in result}
            for sg in sub_goals:
                if sg.id not in seen:
                    result.append(sg)

        return result

    def build_workflow_plan(self, text: str) -> dict:
        goal_type, raw_sub_goals = self.decompose(text)

        if not raw_sub_goals:
            return {
                "goal_text": text,
                "goal_type": goal_type.value,
                "sub_goals": [],
                "execution_order": [],
            }

        ordered = self.topological_sort(raw_sub_goals)
        goal_id = str(uuid.uuid4())[:8]

        self.save_goal(goal_id, text, goal_type, sub_goals=raw_sub_goals)

        return {
            "goal_id": goal_id,
            "goal_text": text,
            "goal_type": goal_type.value,
            "sub_goals": [sg.__dict__ for sg in raw_sub_goals],
            "execution_order": [sg.id for sg in ordered],
        }
