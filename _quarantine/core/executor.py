import json
import logging
import os
import threading
import time
from collections.abc import Callable

from core.async_utils import sync_retry
from core.config import ModelCatalog
from core.decision_logger import get_decision_logger
from core.mode_manager import get_mode_manager
from core.utils import get_project_root as _get_base_dir
from security.code_scan import generated_code_enabled, run_generated_code
from security.engine import get_security_engine
from security.redaction import redact_sensitive

logger = logging.getLogger("jarvis.executor")

BASE_DIR        = _get_base_dir()
API_CONFIG_PATH = BASE_DIR / "config" / "api_keys.json"

# Model names for executor's inline Gemini usage (config-driven with defaults).

_CODE_MODEL = ModelCatalog.GEMINI_FLASH   # "gemini-2.5-flash"
_QUICK_MODEL = ModelCatalog.GEMINI_FLASH_LITE  # "gemini-2.5-flash-lite"


def _executor_model(model_key: str, default: str) -> str:
    """Read a model name from config/models.toml [executor] section."""
    try:
        from core.config import Config
        return Config.instance().get("models", f"executor.{model_key}", default)
    except Exception:
        return default

# Lazy imports for planner/error_handler (may not exist in current architecture)
_create_plan = None
_replan = None
_analyze_error = None
_generate_fix = None
_ErrorDecision = None


def _ensure_planner():
    global _create_plan, _replan
    if _create_plan is None:
        try:
            from core.planner import create_plan, replan
            _create_plan = create_plan
            _replan = replan
        except ImportError:
            def _noop_plan(goal): return {"steps": []}
            def _noop_replan(*a, **kw): return {"steps": []}
            _create_plan = _noop_plan
            _replan = _noop_replan
    return _create_plan, _replan


def _ensure_error_handler():
    global _analyze_error, _generate_fix, _ErrorDecision
    if _analyze_error is None:
        try:
            from core.cog_error_handler import ErrorDecision, analyze_error, generate_fix
            _analyze_error = analyze_error
            _generate_fix = generate_fix
            _ErrorDecision = ErrorDecision
        except ImportError:
            from enum import Enum

            class _ErrorDecision(Enum):
                RETRY = "retry"
                SKIP = "skip"
                ABORT = "abort"
                REPLAN = "replan"

            def _noop_analyze(step, error, attempt=1):
                return {"decision": _ErrorDecision.RETRY, "user_message": "", "reason": ""}

            def _noop_fix(*a, **kw): return {}
            _analyze_error = _noop_analyze
            _generate_fix = _noop_fix
    return _analyze_error, _generate_fix, _ErrorDecision


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


def _generated_code_enabled() -> bool:
    return generated_code_enabled()


def _run_generated_code(description: str, speak: Callable | None = None) -> str:
    return run_generated_code(description, speak)


def _inject_context(params: dict, tool: str, step_results: dict, goal: str = "") -> dict:
    if not step_results:
        return params

    params = dict(params)

    if tool == "file_controller" and params.get("action") in ("write", "create_file"):
        content = params.get("content", "")
        if not content or len(content) < 50:
            all_results = [
                v for v in step_results.values()
                if v and len(v) > 100 and v not in ("Done.", "Completed.")
            ]
            if all_results:
                combined = "\n\n---\n\n".join(all_results)
                translated = _translate_to_goal_language(combined, goal)
                params["content"] = translated
                logger.info("Injected + translated content")

    return params
def _detect_language(text: str) -> str:
    import google.generativeai as genai
    genai.configure(api_key=_get_api_key())
    model = genai.GenerativeModel(_executor_model("quick_model", _QUICK_MODEL))
    try:
        response = model.generate_content(
            f"What language is this text written in? "
            f"Reply with ONLY the language name in English (e.g. Turkish, English, French).\n\n"
            f"Text: {text[:200]}"
        )
        return response.text.strip()
    except Exception:
        return "English"


def _translate_to_goal_language(content: str, goal: str) -> str:
    if not goal:
        return content
    try:
        import google.generativeai as genai
        genai.configure(api_key=_get_api_key())
        model = genai.GenerativeModel(_executor_model("code_model", _CODE_MODEL))

        target_lang = _detect_language(goal)
        logger.info("Translating to: %s", target_lang)

        prompt = (
            f"You are a professional translator. "
            f"Translate the following text into {target_lang}.\n"
            f"IMPORTANT:\n"
            f"- Translate EVERYTHING, leave nothing in English\n"
            f"- Keep all facts, numbers, and data intact\n"
            f"- Keep the structure and formatting\n"
            f"- Output ONLY the translated text, nothing else\n\n"
            f"Text to translate:\n{content[:4000]}"
        )
        response = model.generate_content(prompt)
        translated = response.text.strip()
        logger.info("Translation done (%s)", target_lang)
        return translated
    except Exception:
        logger.warning("Translation failed")
        return content

def _call_tool(tool: str, parameters: dict, speak: Callable | None) -> str:

    if tool == "open_app":
        from actions.open_app import open_app
        return open_app(parameters=parameters, player=None) or "Done."

    elif tool == "web_search":
        from actions.web_search import web_search
        return web_search(parameters=parameters, player=None) or "Done."

    elif tool == "file_controller":
        from actions.file_manager import file_action
        return file_action(parameters.get("action", "list"), parameters) or "Done."

    elif tool == "computer_control":
        from actions.input_control import input_action
        return input_action(parameters.get("action", ""), parameters) or "Done."

    elif tool == "computer_settings":
        from actions.system_settings import settings_action
        return settings_action(parameters.get("action", ""), parameters) or "Done."

    elif tool == "desktop_control":
        from actions.desktop_automation import execute_desktop_action
        return execute_desktop_action(parameters.get("action", ""), parameters) or "Done."

    elif tool == "process_manager":
        from actions.process_manager import process_action
        return process_action(parameters.get("action", "list"), parameters) or "Done."

    elif tool == "shell":
        from actions.shell_exec import shell_action
        return shell_action(parameters.get("action", "run"), parameters) or "Done."

    elif tool == "window_manager":
        from actions.window_manager import window_action
        return window_action(parameters.get("action", "list"), parameters) or "Done."

    elif tool == "clipboard":
        from actions.clipboard_manager import clipboard_action
        return clipboard_action(parameters.get("action", "read"), parameters) or "Done."

    elif tool == "service_manager":
        from actions.service_manager import service_action
        return service_action(parameters.get("action", "list"), parameters) or "Done."

    elif tool == "startup_manager":
        from actions.startup_manager import startup_action
        return startup_action(parameters.get("action", "list"), parameters) or "Done."

    elif tool == "task_scheduler":
        from actions.task_scheduler import task_action
        return task_action(parameters.get("action", "list"), parameters) or "Done."

    elif tool == "network":
        from actions.network_manager import network_action
        return network_action(parameters.get("action", "status"), parameters) or "Done."

    elif tool == "display":
        from actions.display_manager import display_action
        return display_action(parameters.get("action", ""), parameters) or "Done."

    elif tool == "audio":
        from actions.audio_manager import audio_action
        return audio_action(parameters.get("action", ""), parameters) or "Done."

    elif tool == "disk":
        from actions.disk_manager import disk_action
        return disk_action(parameters.get("action", "info"), parameters) or "Done."

    elif tool == "screen":
        from actions.screen_capture import analyze_screen

        from core.config import Config
        api_key = Config.instance().api_keys.get("gemini", "")
        return analyze_screen(prompt=parameters.get("prompt", "Describe what's on screen"), api_key=api_key) or "Done."

    elif tool == "screen_analyzer":
        from actions.screen_analyzer import screen_analyze
        return screen_analyze(parameters) or "Done."

    elif tool == "browser":
        from actions.browser_control import browser_action
        return browser_action(parameters) or "Done."

    elif tool == "generated_code":
        description = parameters.get("description", "")
        if not description:
            raise ValueError("generated_code requires a 'description' parameter.")
        return _run_generated_code(description, speak=speak)

    else:
        logger.error("Unknown tool '%s' - cannot execute", tool)
        return f"I don't know how to use the tool '{tool}' yet, sir. I can use: file_manager, process_manager, shell, browser, screen_analyzer, and more."  # noqa: E501

class AgentExecutor:

    MAX_REPLAN_ATTEMPTS = 2

    def execute(
        self,
        goal:        str,
        speak:       Callable | None        = None,
        cancel_flag: threading.Event | None = None,
    ) -> str:
        create_plan, replan = _ensure_planner()
        analyze_error, generate_fix, ErrorDecision = _ensure_error_handler()

        logger.info("Goal: %s", goal)

        decision_logger = get_decision_logger()
        trace_id = decision_logger.begin_task(goal, source="executor")

        replan_attempts = 0
        completed_steps = []
        step_results    = {}
        plan            = create_plan(goal)
        decision_logger.record(trace_id, "plan.created", {"steps": len(plan.get("steps", [])), "goal": goal[:200]})

        def _log_step_result(step, tool, params, ok, error_msg="", ms=0.0):
            decision_logger.record_tool(
                trace_id, tool, params,
                allowed=True, success=ok,
                duration_ms=ms, error=error_msg,
                mode=get_mode_manager().get_mode().value if hasattr(get_mode_manager().get_mode(), "value") else "",
                session_id="",
            )
            decision_logger.record(trace_id, "tool.executed", {
                "tool": tool, "step": step.get("step", "?"),
                "success": ok, "latency_ms": round(ms, 1),
            })

        while True:
            steps = plan.get("steps", [])

            if not steps:
                msg = "I couldn't create a valid plan for this task, sir."
                decision_logger.record(trace_id, "task.failed", {"error": "no plan steps", "goal": goal[:200], "source": "executor"})  # noqa: E501
                if speak:
                    speak(redact_sensitive(msg))
                return msg

            success      = True
            failed_step  = None
            failed_error = ""

            for step in steps:
                if cancel_flag and cancel_flag.is_set():
                    decision_logger.record(trace_id, "task.cancelled", {"goal": goal[:200], "source": "executor"})
                    if speak:
                        speak(redact_sensitive("Task cancelled, sir."))
                    return "Task cancelled."

                step_num = step.get("step", "?")
                tool     = step.get("tool", "generated_code")
                desc     = step.get("description", "")
                params   = step.get("parameters", {})

                params = _inject_context(params, tool, step_results, goal=goal)

                # Permission check via Mode Manager
                mode_manager = get_mode_manager()
                if not mode_manager.is_allowed(tool):
                    error_msg = f"Tool '{tool}' not allowed in {mode_manager.get_mode()} mode"
                    logger.warning("Permission denied: %s", error_msg)
                    if speak:
                        speak(redact_sensitive(f"I can't do that in {mode_manager.get_mode()} mode, sir."))
                    step_results[step_num] = f"Permission denied: {error_msg}"
                    success = False
                    failed_step = step
                    failed_error = error_msg
                    break

                # Security Engine validation
                security = get_security_engine()
                allowed, sec_reason = security.check_permission(tool, session_id="", params=params)
                if not allowed:
                    logger.warning("Security denied: %s", sec_reason)
                    if speak:
                        speak(redact_sensitive("Security policy blocked that action, sir."))
                    step_results[step_num] = f"Security denied: {sec_reason}"
                    success = False
                    failed_step = step
                    failed_error = sec_reason
                    break

                logger.info("Step %d: [%s] %s", step_num, tool, desc)

                attempt = 1
                step_ok = False

                while attempt <= 3:
                    if cancel_flag and cancel_flag.is_set():
                        break
                    _step_start = time.time()
                    try:
                        result = _call_tool(tool, params, speak)
                        _log_step_result(step, tool, params, True, ms=(time.time() - _step_start) * 1000)
                        step_results[step_num] = result
                        completed_steps.append(step)
                        logger.info("Step %d done: %s", step_num, str(result)[:100])
                        step_ok = True
                        break

                    except Exception as e:
                        error_msg = str(e)
                        _log_step_result(step, tool, params, False, error_msg=error_msg, ms=(time.time() - _step_start) * 1000)  # noqa: E501
                        logger.warning("Step %d attempt %d failed: %s", step_num, attempt, error_msg)

                        recovery = analyze_error(step, error_msg, attempt=attempt)
                        decision = recovery["decision"]
                        user_msg = recovery.get("user_message", "")

                        if speak and user_msg:
                            speak(redact_sensitive(user_msg))

                        if decision == ErrorDecision.RETRY:
                            attempt += 1
                            sync_retry(lambda: None, max_attempts=1, base_delay=2)
                            continue

                        elif decision == ErrorDecision.SKIP:
                            logger.info("Skipping step %d", step_num)
                            completed_steps.append(step)
                            step_ok = True
                            break

                        elif decision == ErrorDecision.ABORT:
                            msg = f"Task aborted, sir. {recovery.get('reason', '')}"
                            decision_logger.record(trace_id, "task.failed", {"error": "abort", "reason": str(recovery.get('reason', ''))[:200], "goal": goal[:200], "source": "executor"})  # noqa: E501
                            if speak:
                                speak(redact_sensitive(msg))
                            return msg

                        else:
                            fix_suggestion = recovery.get("fix_suggestion", "")
                            if fix_suggestion and tool != "generated_code":
                                try:
                                    fixed_step = generate_fix(step, error_msg, fix_suggestion)
                                    if speak:
                                        speak(redact_sensitive("Trying an alternative approach, sir."))
                                    res = _call_tool(
                                        fixed_step["tool"],
                                        fixed_step["parameters"],
                                        speak
                                    )
                                    step_results[step_num] = res
                                    completed_steps.append(step)
                                    step_ok = True
                                    break
                                except Exception:
                                    logger.error("Fix failed")

                            failed_step  = step
                            failed_error = error_msg
                            success      = False
                            break

                if not step_ok and not failed_step:
                    failed_step  = step
                    failed_error = "Max retries exceeded"
                    success      = False

                if not success:
                    break

            if success:
                summary = self._summarize(goal, completed_steps, speak)
                decision_logger.record(trace_id, "task.completed", {
                    "goal": goal[:200], "steps_completed": len(completed_steps), "source": "executor",
                })
                return summary

            if replan_attempts >= self.MAX_REPLAN_ATTEMPTS:
                msg = f"Task failed after {replan_attempts} replan attempts, sir."
                decision_logger.record(trace_id, "task.failed", {
                    "error": "max replans exceeded", "goal": goal[:200], "source": "executor",
                })
                if speak:
                    speak(redact_sensitive(msg))
                return msg

