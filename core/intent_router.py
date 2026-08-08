"""Intent Router - Deterministic pattern matching + LLM fallback for intent classification."""

import re
import json
import logging
from typing import Optional
from dataclasses import dataclass

logger = logging.getLogger("jarvis.cognition.intent")


@dataclass
class Intent:
    """Classified intent with metadata."""
    name: str
    confidence: float
    entities: dict
    source: str  # "pattern" or "llm"


# Precompiled patterns for fast matching
# ORDER MATTERS: more specific patterns first, planner.execute before simple ones
_COMPILED_PATTERNS = [
    # ── Complex Tasks (route to planner) — MUST BE FIRST ──────────────
    (re.compile(r"\b(make|create|build|design|develop|generate)\s+(a\s+)?(ui|interface|dashboard|webpage|page|app|website|html|css|frontend)\b", re.I), "planner.execute", {}),
    (re.compile(r"\b(make|create|build)\s+(me\s+)?(.+)\s+(based on|from|using|with)\s+(what you see|the screen|my screen|current screen)\b", re.I), "planner.execute", {}),
    (re.compile(r"\b(make|create|build)\s+(me\s+)?(a\s+)?(website|web\s*site|web\s*page|webapp)\b", re.I), "planner.execute", {}),
    (re.compile(r"\b(write|generate|create)\s+(a\s+)?(python|script|code|program|automation)\b", re.I), "planner.execute", {}),
    (re.compile(r"\b(set up|setup|configure)\s+(a\s+)?(dev|development|coding|programming)\s+(environment|workspace|setup)\b", re.I), "planner.execute", {}),
    (re.compile(r"\b(organize|sort|clean up|tidy)\s+(my\s+)?(desktop|files?|folder|downloads|documents)\b", re.I), "planner.execute", {}),
    (re.compile(r"\b(research|find out|look into|investigate)\s+(.+)\s+(and|then)\s+(save|write|create|store)\b", re.I), "planner.execute", {}),
    (re.compile(r"\b(take|capture)\s+(a\s+)?(screenshot|screen)\s+(and|then)\s+(analyze|describe|explain)\b", re.I), "planner.execute", {}),
    (re.compile(r"\b(help me|assist me|can you)\s+(make|create|build|write|set up|configure|organize)\b", re.I), "planner.execute", {}),
    (re.compile(r"\b(make|create|build)\s+(a\s+)?(clean|modern|minimal|simple|nice)\s+(looking\s+)?(ui|interface|dashboard|webpage|page|app|website)\b", re.I), "planner.execute", {}),

    # System
    (re.compile(r"\b(exit|quit|shutdown|shut down|goodbye|bye)\b"), "system.exit", {}),
    (re.compile(r"\b(clear|reset|new session|start over)\b"), "system.clear", {}),
    (re.compile(r"\b(settings|configure|config|setup)\b"), "system.config", {}),

    # Queries
    (re.compile(r"\b(what time|current time|time is it)\b"), "query.time", {}),
    (re.compile(r"\b(what date|today.* date|date today|what day)\b"), "query.date", {}),
    (re.compile(r"\b(weather|temperature|forecast)\b"), "query.weather", {"ask_city": True}),

    # Vision
    (re.compile(r"\b(what's on my screen|describe screen|read screen|analyze screen|look at my screen)\b"), "vision.screen_capture", {}),

    # ── Screen Analyzer ────────────────────────────────────────────────
    (re.compile(r"\b(capture|take)\s+(a\s+)?(screenshot|screen)\b", re.I), "action.screen_analyzer", {"action": "analyze_screen"}),
    (re.compile(r"\b(what(?:'s| is) on (?:my )?screen|describe (?:my )?screen|look at (?:my )?screen)\b", re.I), "action.screen_analyzer", {"action": "analyze_screen"}),
    (re.compile(r"\b(analyze|describe)\s+(my\s+)?(screen|display|monitor)\b", re.I), "action.screen_analyzer", {"action": "analyze_screen"}),
    (re.compile(r"\b(look|peek)\s+(through\s+)?(the\s+)?camera\b", re.I), "action.screen_analyzer", {"action": "analyze_camera"}),
    (re.compile(r"\b(webcam|camera)\s+(capture|photo|look)\b", re.I), "action.screen_analyzer", {"action": "analyze_camera"}),
    (re.compile(r"\b(find|locate|where\s+is)\s+(the\s+)?(.+?)\s+(on\s+screen|on\s+the\s+screen)\b", re.I), "action.screen_analyzer", {"action": "find_element", "description": 3}),
    (re.compile(r"\b(click|tap)\s+(the\s+)?(.+?)\s+(on\s+screen|on\s+the\s+screen)\b", re.I), "action.screen_analyzer", {"action": "click_element", "description": 3}),

    # ── Browser Control ────────────────────────────────────────────────
    (re.compile(r"\b(open|go\s+to|navigate\s+to|visit)\s+(.+)\s+(in\s+)?(browser|chrome|edge|firefox)\b", re.I), "action.browser", {"action": "open", "url": 2, "browser": 4}),
    (re.compile(r"\b(open|go\s+to|navigate\s+to|visit)\s+(.+\.com|.+\.org|.+\.net|.+\.io|.+\.dev|.+\.edu|youtube|github|google|reddit|twitter|instagram)\b", re.I), "action.browser", {"action": "open", "url": 2}),
    (re.compile(r"\b(search|google|look\s+up|find)\s+(.+?)\s+(on\s+)?(google|bing|duckduckgo)\b", re.I), "action.browser", {"action": "search", "query": 2, "engine": 4}),
    (re.compile(r"\b(search|google|look\s+up|find)\s+(.+?)\s+(on\s+)?(the\s+)?browser\b", re.I), "action.browser", {"action": "search", "query": 2}),
    (re.compile(r"\b(click|tap)\s+(on\s+)?(.+?)\s+(button|link|text|tab)\b", re.I), "action.browser", {"action": "smart_click", "description": 2}),
    (re.compile(r"\b(type|input|enter|write)\s+(.+?)\s+(into|in)\s+(.+)\b", re.I), "action.browser", {"action": "smart_type", "description": 4, "text": 2}),
    (re.compile(r"\b(scroll)\s+(up|down)\b", re.I), "action.browser", {"action": "scroll", "direction": 2}),
    (re.compile(r"\b(get|read|extract)\s+(page\s+)?(text|content|page)\b", re.I), "action.browser", {"action": "get_text"}),
    (re.compile(r"\b(what\s+)?(page|url|site)\s+(am\s+I\s+on|is\s+this|address)\b", re.I), "action.browser", {"action": "get_url"}),
    (re.compile(r"\b(go\s+back|back\s+button|navigate\s+back)\b", re.I), "action.browser", {"action": "back"}),
    (re.compile(r"\b(go\s+forward|forward\s+button|navigate\s+forward)\b", re.I), "action.browser", {"action": "forward"}),
    (re.compile(r"\b(reload|refresh)\s+(the\s+)?(page|site)\b", re.I), "action.browser", {"action": "reload"}),
    (re.compile(r"\b(new\s+tab|open\s+new\s+tab)\b", re.I), "action.browser", {"action": "new_tab"}),
    (re.compile(r"\b(close\s+tab|close\s+this\s+tab)\b", re.I), "action.browser", {"action": "close_tab"}),
    (re.compile(r"\b(close|quit|exit)\s+(the\s+)?(browser|chrome|edge|firefox)\b", re.I), "action.browser", {"action": "close_all"}),
    (re.compile(r"\b(screenshot|capture)\s+(the\s+)?(page|site|browser)\b", re.I), "action.browser", {"action": "screenshot"}),

    # Desktop control
    (re.compile(r"\b(volume up|volume down|mute|unmute|play media|pause media|next track|previous track|minimize all|show desktop|task manager)\b"), "action.desktop_control", {}),

    # Memory
    (re.compile(r"\b(search memory|semantic memory|vector memory|remember when)\s+(.+)"), "memory.vector_query", {"query": 2}),
    (re.compile(r"\b(remember that|my name is|I am|I'm)\s+(.+)"), "memory.store", {"fact": 2}),
    (re.compile(r"\b(what do you know about me|my preferences|what do you remember)\b"), "memory.query", {}),

    # Search
    (re.compile(r"\b(search|look up|find|google)\s+(.+)"), "action.search", {"query": 2}),

    # Open apps
    (re.compile(r"\b(open|launch|start|run)\s+(.+)"), "action.open", {"app": 2}),

    # Notes & reminders
    (re.compile(r"\b(remind me|set reminder|alarm)\s+(.+)"), "action.reminder", {"details": 2}),
    (re.compile(r"\b(note|write down|jot|save)\s+(.+)"), "action.note", {"content": 2}),

    # Research & math
    (re.compile(r"\b(tell me about|explain)\s+(.+)"), "action.research", {"topic": 2}),
    (re.compile(r"\b(calculate|math|compute)\s+(.+)"), "action.calculate", {"expression": 2}),
    (re.compile(r"\bwhat is\s+(.+)"), "action.calculate", {"expression": 1}),

    # Greetings
    (re.compile(r"\b(hello|hi|hey|sup|greetings)\b"), "meta.greet", {}),
    (re.compile(r"\b(how do you feel|you doing|how's it going)\b"), "meta.greet", {}),
    (re.compile(r"\bhow are you\b"), "meta.howareyou", {}),
    (re.compile(r"\b(thank|thanks|thx)\b"), "meta.thanks", {}),
    (re.compile(r"\b(help|what can you do|capabilities)\b"), "meta.help", {}),

    # ── File Management ───────────────────────────────────────────────
    (re.compile(r"\b(list|show|display)\s+(files?|folder|directory|contents?)\s+(in|of|at)?\s*(.*)", re.I), "action.file", {"action": "list", "path": 4}),
    (re.compile(r"\b(read|open|cat|show)\s+(file|text)\s+(.+)"), "action.file", {"action": "read", "path": 3}),
    (re.compile(r"\b(write|save|create)\s+(file|text)\s+(.+)\s+(to|in|at)\s+(.+)"), "action.file", {"action": "write", "content": 3, "path": 5}),
    (re.compile(r"\b(create|make)\s+(file|folder|directory)\s+(.+)"), "action.file", {"action": "create", "path": 3}),
    (re.compile(r"\b(delete|remove|trash)\s+(file|folder)?\s*(.+)"), "action.file", {"action": "delete", "path": 3}),
    (re.compile(r"\b(copy|duplicate)\s+(.+)\s+(to|into)\s+(.+)"), "action.file", {"action": "copy", "source": 2, "destination": 4}),
    (re.compile(r"\b(move|transfer)\s+(.+)\s+(to|into)\s+(.+)"), "action.file", {"action": "move", "source": 2, "destination": 4}),
    (re.compile(r"\b(rename)\s+(.+)\s+(to|as)\s+(.+)"), "action.file", {"action": "rename", "path": 2, "new_name": 4}),
    (re.compile(r"\bsearch\s+(for\s+)?files?\s+(.+)"), "action.file", {"action": "search", "query": 2}),
    (re.compile(r"\b(file\s+info|info\s+on\s+file)\s+(.+)"), "action.file", {"action": "info", "path": 2}),
    (re.compile(r"\b(where is|where's)\s+(.+)"), "action.file", {"action": "exists", "path": 2}),
    (re.compile(r"\b(make|create)\s+(a\s+)?folder\s+(.+)"), "action.file", {"action": "mkdir", "path": 3}),
    (re.compile(r"\b(how big|size of|folder size|disk usage)\s+(.*)"), "action.file", {"action": "size", "path": 2}),

    # ── Process Management ────────────────────────────────────────────
    (re.compile(r"\b(list|show|running)\s+(processes?|programs?|apps?)\b"), "action.process", {"action": "list"}),
    (re.compile(r"\b(kill|stop|end|terminate)\s+(process|program|app)?\s*(.+)"), "action.process", {"action": "kill", "name": 3}),
    (re.compile(r"\bfind\s+(process|program)\s+(.+)"), "action.process", {"action": "search", "query": 2}),
    (re.compile(r"\b(top|most)\s+(cpu|processor)\s+(processes?|programs?)\b"), "action.process", {"action": "top"}),
    (re.compile(r"\b(top|most)\s+(memory|ram)\s+(processes?|programs?)\b"), "action.process", {"action": "top_mem"}),

    # ── Shell Execution ───────────────────────────────────────────────
    (re.compile(r"\b(run|execute|shell|cmd|command)\s+(.+)"), "action.shell", {"action": "run", "command": 2}),
    (re.compile(r"\b(powershell|ps)\s+(.+)"), "action.shell", {"action": "powershell", "command": 2}),
    (re.compile(r"\b(pip\s+install|install\s+package)\s+(.+)"), "action.shell", {"action": "pip", "packages": 2}),
    (re.compile(r"\b(pip\s+uninstall|uninstall\s+package)\s+(.+)"), "action.shell", {"action": "pip", "packages": 2}),

    # ── Window Management ─────────────────────────────────────────────
    (re.compile(r"\b(list|show|all)\s+windows?\b"), "action.window", {"action": "list"}),
    (re.compile(r"\b(switch to|focus|bring|go to)\s+(.+)"), "action.window", {"action": "focus", "name": 2}),
    (re.compile(r"\b(close)\s+(window|app|program)\s*(.*)"), "action.window", {"action": "close", "name": 3}),
    (re.compile(r"\b(minimize)\s+(window|app)?\s*(.*)"), "action.window", {"action": "minimize", "name": 3}),
    (re.compile(r"\b(maximize)\s+(window|app)?\s*(.*)"), "action.window", {"action": "maximize", "name": 3}),
    (re.compile(r"\b(snap)\s+(left|right)\b"), "action.window", {"action": "snap_left"}),
    (re.compile(r"\b(fullscreen|full screen)\b"), "action.window", {"action": "fullscreen"}),
    (re.compile(r"\b(active|current)\s+window\b"), "action.window", {"action": "title"}),

    # ── Clipboard ─────────────────────────────────────────────────────
    (re.compile(r"\b(copy|clipboard)\s+(.+)"), "action.clipboard", {"action": "write", "text": 2}),
    (re.compile(r"\b(paste|clipboard|what.* copied)\b"), "action.clipboard", {"action": "read"}),
    (re.compile(r"\b(clear)\s+(clipboard|copied)\b"), "action.clipboard", {"action": "clear"}),

    # ── System Settings ───────────────────────────────────────────────
    (re.compile(r"\b(brightness)\s+(to\s+)?(\d+)\b"), "action.settings", {"action": "brightness", "level": 3}),
    (re.compile(r"\b(brightness)\s+(up|increase|higher)\b"), "action.settings", {"action": "brightness", "level": "75"}),
    (re.compile(r"\b(brightness)\s+(down|decrease|lower)\b"), "action.settings", {"action": "brightness", "level": "25"}),
    (re.compile(r"\b(get|check|what.* brightness)\b"), "action.settings", {"action": "get_brightness"}),
    (re.compile(r"\b(wifi|wi-fi|wireless)\s+(on|enable|turn on)\b"), "action.settings", {"action": "wifi_on"}),
    (re.compile(r"\b(wifi|wi-fi|wireless)\s+(off|disable|turn off)\b"), "action.settings", {"action": "wifi_off"}),
    (re.compile(r"\b(wifi|wi-fi|wireless)\s+status\b"), "action.settings", {"action": "wifi_status"}),
    (re.compile(r"\b(bluetooth)\s+(on|enable)\b"), "action.settings", {"action": "bluetooth_on"}),
    (re.compile(r"\b(bluetooth)\s+(off|disable)\b"), "action.settings", {"action": "bluetooth_off"}),
    (re.compile(r"\b(shutdown|power off|turn off)\s+(the\s+)?(computer|pc|laptop)\b"), "action.settings", {"action": "shutdown"}),
    (re.compile(r"\b(restart|reboot)\s+(the\s+)?(computer|pc|laptop)\b"), "action.settings", {"action": "restart"}),
    (re.compile(r"\b(sleep|suspend|standby)\b"), "action.settings", {"action": "sleep"}),
    (re.compile(r"\b(hibernate)\b"), "action.settings", {"action": "hibernate"}),
    (re.compile(r"\b(lock)\s+(screen|computer|pc)\b"), "action.settings", {"action": "lock"}),
    (re.compile(r"\b(airplane|flight)\s+mode\s+(on|off)\b"), "action.settings", {"action": "airplane_on"}),

    # ── Input Control ─────────────────────────────────────────────────
    (re.compile(r"\b(click|tap|press)\s+(at\s+)?(\d+)[,\s]+(\d+)\b"), "action.input", {"action": "mouse_click", "x": 3, "y": 4}),
    (re.compile(r"\b(double\s*click|double\s*tap)\s+(at\s+)?(\d+)[,\s]+(\d+)\b"), "action.input", {"action": "mouse_double_click", "x": 3, "y": 4}),
    (re.compile(r"\b(right\s*click)\s+(at\s+)?(\d+)[,\s]+(\d+)\b"), "action.input", {"action": "mouse_right_click", "x": 3, "y": 4}),
    (re.compile(r"\b(move\s+mouse|cursor\s+to)\s+(to\s+)?(\d+)[,\s]+(\d+)\b"), "action.input", {"action": "mouse_move", "x": 3, "y": 4}),
    (re.compile(r"\b(scroll\s+(up|down))\b"), "action.input", {"action": "mouse_scroll"}),
    (re.compile(r"\b(type|input|enter)\s+(.+)"), "action.input", {"action": "type_text", "text": 2}),
    (re.compile(r"\b(press|hit|tap)\s+(key\s+)?(.+)"), "action.input", {"action": "press_key", "key": 3}),
    (re.compile(r"\b(hotkey|shortcut|combo)\s+(.+)"), "action.input", {"action": "hotkey", "keys": 2}),
    (re.compile(r"\b(where\s+is|mouse\s+position)\b"), "action.input", {"action": "get_mouse_pos"}),
    (re.compile(r"\b(screen\s+size|resolution)\b"), "action.input", {"action": "get_screen_size"}),
    (re.compile(r"\b(take\s+)?screenshot\b"), "action.input", {"action": "screenshot"}),

    # ── Network ───────────────────────────────────────────────────────
    (re.compile(r"\b(network|internet)\s+(status|info)\b"), "action.network", {"action": "status"}),
    (re.compile(r"\b(what's?\s+my|my)\s+(ip|address)\b"), "action.network", {"action": "ip"}),
    (re.compile(r"\b(public\s+ip|external\s+ip)\b"), "action.network", {"action": "ip", "public": True}),
    (re.compile(r"\b(scan|find|list)\s+(wifi|wireless|networks?)\b"), "action.network", {"action": "wifi_scan"}),
    (re.compile(r"\b(connect\s+to|join)\s+(wifi|wireless)\s+(.+)"), "action.network", {"action": "wifi_connect", "ssid": 3}),
    (re.compile(r"\b(ping|test|check)\s+(connection|connectivity)\b"), "action.network", {"action": "ping"}),
    (re.compile(r"\b(ping)\s+(.+)"), "action.network", {"action": "ping", "host": 2}),
    (re.compile(r"\bspeed\s*test\b"), "action.network", {"action": "speed_test"}),
    (re.compile(r"\b(network\s+)?interfaces?\b"), "action.network", {"action": "interfaces"}),

    # ── Services ──────────────────────────────────────────────────────
    (re.compile(r"\b(list|show|running)\s+services?\b"), "action.service", {"action": "list"}),
    (re.compile(r"\b(start|enable)\s+(service|svc)\s+(.+)"), "action.service", {"action": "start", "name": 3}),
    (re.compile(r"\b(stop|disable)\s+(service|svc)\s+(.+)"), "action.service", {"action": "stop", "name": 3}),
    (re.compile(r"\b(restart)\s+(service|svc)\s+(.+)"), "action.service", {"action": "restart", "name": 3}),
    (re.compile(r"\b(service|svc)\s+status\s+(.+)"), "action.service", {"action": "status", "name": 2}),

    # ── Disk ──────────────────────────────────────────────────────────
    (re.compile(r"\b(disk|drive)\s+(info|status|space)\b"), "action.disk", {"action": "info"}),
    (re.compile(r"\b(cleanup|clean up|free space)\b"), "action.disk", {"action": "cleanup"}),
    (re.compile(r"\b(clean|clear)\s+temp\b"), "action.disk", {"action": "temp_clean"}),
    (re.compile(r"\b(empty|clear)\s+(recycle|trash)\b"), "action.disk", {"action": "recycle"}),
    (re.compile(r"\b(disk|drive)\s+health\b"), "action.disk", {"action": "disk_health"}),

    # ── Audio ─────────────────────────────────────────────────────────
    (re.compile(r"\b(audio|speaker|headphone)\s+devices?\b"), "action.audio", {"action": "devices"}),
    (re.compile(r"\b(switch\s+to|use)\s+(speaker|headphone|headset|mic)\s*(.*)"), "action.audio", {"action": "set_output", "name": 3}),
    (re.compile(r"\b(volume)\s+(to\s+)?(\d+)\b"), "action.audio", {"action": "volume", "level": 3}),
    (re.compile(r"\b(volume)\s+(up|down)\b"), "action.audio", {"action": "volume"}),
    (re.compile(r"\btest\s+(speaker|audio|sound)\b"), "action.audio", {"action": "test_speakers"}),

    # ── Display ───────────────────────────────────────────────────────
    (re.compile(r"\b(set\s+)?resolution\s+(to\s+)?(\d+)[x\s]+(\d+)\b"), "action.display", {"action": "resolution", "width": 3, "height": 4}),
    (re.compile(r"\b(list|show)\s+monitors?\b"), "action.display", {"action": "monitors"}),
    (re.compile(r"\b(set|change)\s+wallpaper\s+(to\s+)?(.+)"), "action.display", {"action": "wallpaper", "path": 3}),
    (re.compile(r"\bwhat('s| is)\s+(my\s+)?wallpaper\b"), "action.display", {"action": "get_wallpaper"}),

    # ── Startup ───────────────────────────────────────────────────────
    (re.compile(r"\b(list|show)\s+startup\s+(programs?|apps?)\b"), "action.startup", {"action": "list"}),
    (re.compile(r"\b(add|set)\s+(.+)\s+to\s+startup\b"), "action.startup", {"action": "add", "name": 2}),
    (re.compile(r"\b(remove|delete)\s+(.+)\s+from\s+startup\b"), "action.startup", {"action": "remove", "name": 2}),

    # ── Scheduled Tasks ───────────────────────────────────────────────
    (re.compile(r"\b(list|show)\s+scheduled\s+tasks?\b"), "action.tasks", {"action": "list"}),
    (re.compile(r"\b(run|start)\s+(task|scheduled)\s+(.+)"), "action.tasks", {"action": "run", "name": 3}),
    (re.compile(r"\b(delete|remove)\s+(task|scheduled)\s+(.+)"), "action.tasks", {"action": "delete", "name": 3}),
]


class IntentRouter:
    """Routes user input to the correct intent handler.

    Uses a two-tier approach:
    1. Deterministic pattern matching (fast, no LLM needed)
    2. LLM-based classification (for complex/ambiguous inputs)
    """

    def __init__(self):
        self._patterns = _COMPILED_PATTERNS

    def classify(self, text: str) -> Intent:
        """Classify user input into an intent."""
        text_lower = text.lower().strip()

        for pattern, intent_name, extractors in self._patterns:
            match = pattern.search(text_lower)
            if match:
                entities = {}
                for key, val in extractors.items():
                    if isinstance(val, int) and val <= len(match.groups()):
                        entities[key] = match.group(val)
                    else:
                        entities[key] = val

                logger.info("Pattern match: %s (%.1f%%)", intent_name, 100)
                return Intent(
                    name=intent_name,
                    confidence=1.0,
                    entities=entities,
                    source="pattern",
                )

        logger.info("No pattern match, routing to general.chat")
        return Intent(
            name="general.chat",
            confidence=0.5,
            entities={"text": text},
            source="default",
        )

    def classify_with_llm(self, text: str, llm_response: Optional[str] = None) -> Intent:
        """Classify using LLM when pattern matching is uncertain."""
        if llm_response:
            return self._parse_llm_classification(llm_response, text)
        return self.classify(text)

    def _parse_llm_classification(self, response: str, original_text: str) -> Intent:
        """Parse LLM's intent classification response."""
        try:
            data = json.loads(response)
            return Intent(
                name=data.get("intent", "general.chat"),
                confidence=data.get("confidence", 0.7),
                entities=data.get("entities", {}),
                source="llm",
            )
        except (json.JSONDecodeError, AttributeError):
            return Intent(
                name="general.chat",
                confidence=0.5,
                entities={"text": original_text},
                source="llm_fallback",
            )
