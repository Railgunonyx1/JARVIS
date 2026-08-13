import json
import re

from core.mode_manager import ExecutionMode, get_mode_manager
from core.utils import get_project_root as get_base_dir

BASE_DIR        = get_base_dir()
API_CONFIG_PATH = BASE_DIR / "config" / "api_keys.json"

# Model names are configurable via config/models.toml [planner] section.
# Fall back to sensible defaults when config is absent.
_PLANNER_MODEL = "gemini-2.5-flash-lite"
_REPLAN_MODEL = "gemini-2.5-flash"


def _get_planner_models() -> tuple[str, str]:
    """Return (plan_model, replan_model) from config, with defaults."""
    try:
        from core.config import Config
        cfg = Config.instance().get("models", "planner") or {}
        plan = cfg.get("plan_model", _PLANNER_MODEL)
        replan = cfg.get("replan_model", _REPLAN_MODEL)
        return plan, replan
    except Exception:
        return _PLANNER_MODEL, _REPLAN_MODEL

# The exact tool names AgentExecutor._call_tool() can dispatch. The planner
# advertises ONLY these (filtered by mode), so the LLM can't invent tools and
# every produced plan validates against the real executor.
EXEC_TOOLS = {
    "open_app": "Launch installed applications (app_name)",
    "web_search": "Search the web (query)",
    "file_controller": "Read/write/list files (action: read|write|list, path, content)",
    "computer_control": "Keyboard/mouse input (action: type_text|click|key_press, text)",
    "computer_settings": "System settings (action, value)",
    "desktop_control": "Desktop automation (action, parameters)",
    "process_manager": "Manage processes (action: list|kill|start, name)",
    "shell": "Run shell commands (action: run|powershell|python|pip, command)",
    "window_manager": "Manage windows (action: list|focus|close|minimize|maximize, name)",
    "clipboard": "Clipboard operations (action: read|write|clear, text)",
    "service_manager": "Manage services (action: list|start|stop|restart, name)",
    "startup_manager": "Manage startup items (action: list|add|remove, name)",
    "task_scheduler": "Schedule tasks (action: list|create|delete, name)",
    "network": "Network info (action: status|public_ip|speed_test|dns, host)",
    "display": "Display control (action, value)",
    "audio": "Audio control (action: volume|mute|record|list, value)",
    "disk": "Disk info and cleanup (action: info|temp_clean)",
    "screen": "Capture and analyze the screen (action: capture|analyze, prompt)",
    "screen_analyzer": "Analyze the screen (prompt)",
    "browser": "Browser automation (action: open|search|navigate, url, query)",
    "generated_code": "Write and run generated code/UI/HTML (description)",
}


def _get_mode_tools(mode: ExecutionMode) -> list:
    """Executor tool names available in the given mode."""
    mode_manager = get_mode_manager()
    return [name for name in EXEC_TOOLS if mode_manager.is_allowed(name, mode)]


def _build_planner_prompt(mode: ExecutionMode = ExecutionMode.SMART) -> str:
    """Build planner prompt with tools filtered by current execution mode."""
    available_tools = _get_mode_tools(mode)

    tools_section = "\n\n".join(
        f"{name}: {desc}" for name, desc in EXEC_TOOLS.items() if name in available_tools
    ) if available_tools else "(no tools available)"

    return f"""You are the planning module of JARVIS MK-X, a personal AI assistant.
Your job: break any user goal into a sequence of steps using ONLY the tools listed below.

EXECUTION MODE: {str(mode).upper()}
{_get_mode_description(mode)}

ABSOLUTE RULES:
- ONLY use the tools listed below. Do NOT invent tool names.
- Max 5 steps. Use the minimum steps needed.
- Use web_search for ANY information retrieval, research, or current data.
- Use file_controller to save/create/read files.
- Use screen_analyzer for screenshots and screen analysis.
- Use generated_code for writing code, creating UIs, generating HTML/CSS/JS, or any programming task.

AVAILABLE TOOLS (use exactly these names):

{tools_section}

EXAMPLES:

Goal: "make me a clean looking UI based on what you see on the screen"
Steps:
screen_analyzer | action: analyze_screen, prompt: "Describe the current screen layout and UI elements"
generated_code | description: "Create a clean modern HTML/CSS/JS UI dashboard based on the screen description above. Save to desktop."

Goal: "research mechanical engineering and save it"
Steps:
web_search | query: "mechanical engineering overview"
web_search | query: "mechanical engineering applications"
file_controller | action: write, path: ~/Desktop/mechanical_engineering.txt, content: "..."

Goal: "What is the price of Bitcoin"
Steps:
web_search | query: "Bitcoin price today USD"

Goal: "open notepad and type hello world"
Steps:
open_app | app_name: notepad
computer_control | action: type_text, text: "hello world"

Goal: "list running processes and kill chrome"
Steps:
process_manager | action: list
process_manager | action: kill, name: chrome

Goal: "check disk space and clean temp files"
Steps:
disk | action: info
disk | action: temp_clean

Goal: "open YouTube and search for cooking tutorials"
Steps:
browser | action: open, url: youtube.com
browser | action: search, query: "cooking tutorials"

Goal: "what's on my screen right now"
Steps:
screen_analyzer | action: analyze_screen, prompt: "Describe everything visible on the screen"

OUTPUT — return ONLY valid JSON, no markdown, no explanation, no code blocks:
{{
  "goal": "...",
  "steps": [
    {{
      "step": 1,
      "tool": "tool_name",
      "description": "what this step does",
      "parameters": {{}},
      "critical": true
    }}
  ]
}}
"""


def _get_mode_description(mode: ExecutionMode) -> str:
    """Get human-readable mode description."""
    descriptions = {
        ExecutionMode.CONTROLLED: "CONTROLLED MODE: Only safe, non-destructive actions available. No confirmations needed.",
        ExecutionMode.SMART: "SMART MODE: Most actions available. Risky operations require confirmation.",
        ExecutionMode.AGENT: "AGENT MODE: Full access within sandbox. Critical system changes require confirmation.",
    }
    return descriptions.get(mode, "")


# Keep original PLANNER_PROMPT as fallback for backward compatibility
PLANNER_PROMPT = _build_planner_prompt(ExecutionMode.SMART)


def _get_api_key() -> str:
    import os
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


def create_plan(goal: str, context: str = "", mode: ExecutionMode = None) -> dict:
    import google.generativeai as genai

    if mode is None:
        mode_manager = get_mode_manager()
        mode = mode_manager.get_mode()

    # Build dynamic prompt based on current mode
    dynamic_prompt = _build_planner_prompt(mode)

    genai.configure(api_key=_get_api_key())
    plan_model, _ = _get_planner_models()
    model = genai.GenerativeModel(
        model_name=plan_model,
        system_instruction=dynamic_prompt
    )

    user_input = f"Goal: {goal}"
    if context:
        user_input += f"\n\nContext: {context}"

    try:
        response = model.generate_content(user_input)
        text     = response.text.strip()
        text     = re.sub(r"```(?:json)?", "", text).strip().rstrip("`").strip()

        plan = json.loads(text)

        if "steps" not in plan or not isinstance(plan["steps"], list):
            raise ValueError("Invalid plan structure")

        for step in plan["steps"]:
            tool = step.get("tool", "")
            # Validate against the real executor tool set + mode permissions
            mode_manager = get_mode_manager()
            if tool not in EXEC_TOOLS or not mode_manager.is_allowed(tool, mode):
                print(f"[Planner] Tool '{tool}' not allowed in {str(mode)} mode (allowed: {_get_mode_tools(mode)}) - replacing with generated_code")
                step["tool"] = "generated_code"
                step["parameters"] = {"description": step.get("description", f"Do: {tool}")}

        print(f"[Planner] OK: Plan: {len(plan['steps'])} steps")
        for s in plan["steps"]:
            print(f"  Step {s['step']}: [{s['tool']}] {s['description']}")

        return plan

    except json.JSONDecodeError as e:
        print(f"[Planner] WARN: JSON parse failed: {e}")
        return _fallback_plan(goal)
    except Exception as e:
        print(f"[Planner] WARN: Planning failed: {e}")
        return _fallback_plan(goal)


def _fallback_plan(goal: str) -> dict:
    print("[Planner] INFO: Fallback plan")
    return {
        "goal": goal,
        "steps": [
            {
                "step": 1,
                "tool": "web_search",
                "description": f"Search for: {goal}",
                "parameters": {"query": goal},
                "critical": True
            }
        ]
    }


def replan(goal: str, completed_steps: list, failed_step: dict, error: str) -> dict:
    import google.generativeai as genai

    genai.configure(api_key=_get_api_key())
    _, replan_model = _get_planner_models()
    model = genai.GenerativeModel(
        model_name=replan_model,
        system_instruction=PLANNER_PROMPT
    )

    completed_summary = "\n".join(
        f"  - Step {s['step']} ({s['tool']}): DONE" for s in completed_steps
    )

    prompt = f"""Goal: {goal}

Already completed:
{completed_summary if completed_summary else '  (none)'}

Failed step: [{failed_step.get('tool')}] {failed_step.get('description')}
Error: {error}

Create a REVISED plan for the remaining work only. Do not repeat completed steps."""

    try:
        response = model.generate_content(prompt)
        text     = response.text.strip()
        text     = re.sub(r"```(?:json)?", "", text).strip().rstrip("`").strip()
        plan     = json.loads(text)

        for step in plan.get("steps", []):
            tool = step.get("tool", "")
            if tool not in EXEC_TOOLS:
                print(f"[Planner] Replan: unknown tool '{tool}' - replacing with generated_code")
                step["tool"] = "generated_code"
                step["parameters"] = {"description": step.get("description", f"Do: {tool}")}

        print(f"[Planner] INFO: Revised plan: {len(plan['steps'])} steps")
        return plan
    except Exception as e:
        print(f"[Planner] WARN: Replan failed: {e}")
        return _fallback_plan(goal)
