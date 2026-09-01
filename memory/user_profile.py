"""User Profile Memory Module — persistent user profile loaded at every DSH/JARVIS startup.

This module stores the detailed non-personal profile of the user's technical interests,
development approach, UI preferences, projects, and working style. It's loaded into
the memory system at bootstrap so the agent always has this context.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


USER_PROFILE = {
    "technical_interests": {
        "core": [
            "AI agents and LLM systems",
            "Local AI / Ollama",
            "AI model routing and fallback systems",
            "MCP (Model Context Protocol)",
            "Agentic architectures",
            "AI memory systems",
            "Vector databases",
            "Desktop automation",
            "Multimodal AI",
            "Speech-to-text and text-to-speech",
            "Terminal applications",
        ],
        "stack": [
            "React/TypeScript applications",
            "Python backends",
            "Electron",
            "FastAPI / Flask",
            "SQLite",
            "WebSockets",
            "Vite",
            "Tailwind CSS",
            "Zustand",
            "GitHub repositories",
        ],
        "practices": [
            "Software architecture",
            "Performance optimization",
            "Security auditing",
            "Automated testing",
            "UI/UX design",
        ],
        "philosophy": "Interested in how systems work internally, not just how to use them.",
    },
    "development_approach": {
        "audit_style": "Deep audits over superficial reviews — architecture → implementation → integration → testing → reliability → UI → release readiness all checked.",
        "workflow": "Iterative: batch changes → inspect repo → fix problems → re-audit → repeat until issues are small.",
        "verification": "Frequently asks for second or third verification after changes.",
        "advice_preference": "Practical over theoretical — concrete fixes, specific files, specific architectural changes, implementation priorities, actual commands, tests, before/after comparisons.",
    },
    "ui_preferences": {
        "favored": [
            "Clean",
            "Dense but readable",
            "Professional",
            "Functional",
            "Modern",
            "Terminal-oriented when appropriate",
            "Information-rich without being cluttered",
        ],
        "reference": "Claude Code's UI philosophy",
        "disliked": [
            "Generic",
            "Overly flashy",
            "Cluttered",
            "\"AI-looking\" for the sake of looking AI",
            "Full of unnecessary controls",
        ],
        "philosophy": "Functionality-driven UI design.",
    },
    "projects": {
        "StudyCore": {
            "domain": "Education (CBSE, JEE, NEET)",
            "frontend": ["React", "Vite", "TypeScript", "Tailwind"],
            "desktop": ["Electron"],
            "backend": ["SQLite", "Python/Flask"],
            "ai": ["Ollama (Mistral, Phi, Llama)"],
            "planned_features": [
                "AI tutor",
                "OCR",
                "Flashcards",
                "Spaced repetition",
                "Planner",
                "Knowledge graph",
                "Exam simulation",
                "AI-assisted studying",
            ],
            "notes": "Multiple visual themes, lightweight desktop experience.",
        },
        "WealthWise": {
            "domain": "Finance",
            "stack": ["React 19", "TypeScript", "Vite", "Tailwind CSS v4", "FastAPI"],
            "notes": "Prefers modern frameworks for new projects.",
        },
    },
    "hardware_interests": {
        "components": ["CPUs", "GPUs", "RAM", "SSDs", "NVIDIA hardware"],
        "focus": ["Gaming performance", "Windows performance", "Driver issues", "CPU/GPU utilization", "FPS troubleshooting"],
        "investigations": "Hardware utilization vs. observed gaming performance mismatches.",
    },
    "gaming_interests": {
        "games": ["BeamNG.drive", "Minecraft", "Forza Horizon 5", "Roblox", "F1"],
        "beamng_style": "Very difficult career challenges with reasonable progression/multipliers; difficulty through gameplay constraints, not artificial damage multipliers.",
    },
    "open_source_approach": {
        "evaluation_criteria": [
            "What does this project do?",
            "Is it worth incorporating?",
            "What architecture does it use?",
            "What could JARVIS borrow from it?",
            "What ideas are actually useful?",
            "What should be added to your roadmap?",
        ],
        "philosophy": "Use existing open-source projects as architecture references, not blind copies.",
        "investigated": [
            "Open Interpreter",
            "OpenAI/Codex-related tooling",
            "Agentic design patterns",
            "AI memory systems",
            "Anti-detect browsers",
            "Other open-source AI-agent infrastructure",
        ],
    },
    "electronics_robotics": {
        "hardware": ["LCD", "Joystick", "Telemetry", "Multiple telemetry screens", "Screen navigation"],
        "interaction_model": "Joystick → navigate telemetry screens (deliberately simple)",
        "philosophy": "Display focuses on telemetry, not a general-purpose control panel.",
    },
    "documentation_philosophy": {
        "qualities": ["Structured", "Consistent with actual implementation", "Divided into logical sections", "Kept synchronized with architecture changes"],
        "practice": "Compare repository changes against existing implementation plan/documentation.",
    },
    "project_planning": {
        "style": "Detailed implementation plans with phases, blocks, priorities, architecture contracts, P0/P1/P2 severity, milestones, test requirements, release gates.",
        "terminology": ["P0", "P1", "P2", "Block 1", "Block 2", "Block 3", "Sprint milestones", "Architecture contract", "Release readiness"],
        "preference": "Defined target architecture before large changes.",
    },
    "performance_concerns": [
        "Startup time",
        "Memory usage",
        "CPU utilization",
        "Latency",
        "TTFT",
        "Model-loading overhead",
        "Polling",
        "Event-loop blocking",
        "Application responsiveness",
        "Resource consumption",
    ],
    "performance_focus": "Making local AI practical on consumer hardware.",
    "reliability_concerns": [
        "Graceful fallbacks",
        "Connection recovery",
        "Model failures",
        "Timeouts",
        "Hung processes",
        "Startup failures",
        "WebSocket reliability",
        "Test reliability",
        "Dependency problems",
        "Cross-platform behavior",
    ],
    "reliability_philosophy": "\"The feature works when everything goes right\" is not sufficient. Must handle: network disappears, model crashes, tool fails, process hangs, environment isn't what we expected.",
    "security_concerns": [
        "Dependency vulnerabilities",
        "RCE risks",
        "Authentication",
        "Token handling",
        "Tool permissions",
        "Desktop automation security",
        "Sandboxing",
        "Input validation",
    ],
    "security_tools": ["pip-audit"],
    "feedback_style": {
        "preference": "Direct criticism",
        "looking_for": [
            "What is actually wrong",
            "What is merely mediocre",
            "What is good",
            "What is unnecessary",
            "What should be deleted",
            "What should be redesigned",
            "What is release-blocking",
            "What can wait",
        ],
        "avoid": "Automatic agreement — bad architectural decisions should be identified as such.",
    },
    "feature_creep_attitude": {
        "preference": "Removing unnecessary functionality",
        "examples": [
            "Telemetry project: narrowed design rather than adding controls",
            "JARVIS: moving toward smaller, more coherent architecture",
        ],
        "philosophy": "More capability per component, fewer unnecessary components.",
    },
    "technology_philosophy": "Open source + local-first capability + modular architecture + AI + automation + strong UI + aggressive testing. Intersection: AI → Agent → Tools → Computer → Automation → Verification.",
    "common_requests": [
        "Audit this repository",
        "Re-audit it",
        "Check the changes",
        "Find remaining errors",
        "Compare it against the plan",
        "Find architectural problems",
        "Optimize it",
        "Make it more reliable",
        "Improve the UI",
        "Find open-source projects worth using",
        "Research a technology",
        "Determine whether an idea is actually worth implementing",
        "Create implementation plans",
        "Turn plans into concrete changes",
        "Check whether changes introduced regressions",
        "Find edge cases",
        "Determine what should be removed",
    ],
    "summary": "Student/developer experimenting with AI agents, software architecture, local LLMs, automation, modern web/desktop stacks, and hardware projects. Prefers ambitious systems but increasingly cares about reducing complexity, improving reliability, and making the final product feel polished rather than merely feature-rich. Uses iterative repository audits and testing as a major part of development process. Prefers direct technical criticism over automatic agreement.",
}


def get_user_profile() -> dict[str, Any]:
    """Return the complete user profile as a dictionary."""
    return USER_PROFILE.copy()


def get_user_profile_summary() -> str:
    """Return a concise text summary for prompt injection."""
    return USER_PROFILE["summary"]


def get_user_profile_path() -> Path:
    """Path to the persisted user profile JSON file."""
    return Path(__file__).parent / "user_profile.json"


def persist_user_profile() -> None:
    """Write the user profile to disk for external tooling."""
    path = get_user_profile_path()
    with open(path, "w", encoding="utf-8") as f:
        json.dump(USER_PROFILE, f, indent=2)


def load_user_profile() -> dict[str, Any]:
    """Load the user profile from disk (falls back to in-memory constant)."""
    path = get_user_profile_path()
    if path.exists():
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return USER_PROFILE.copy()


def inject_into_memory_api(api) -> int:
    """
    Inject the user profile into the MemoryAPI as CORE MEMORY entries.

    This should be called during MemoryAPI initialization (after KV store is ready)
    so that format_for_prompt() always includes this profile in [CORE MEMORY].

    Returns the number of entries stored.
    """
    if api is None or api._controller is None or api._controller._kv is None:
        return 0

    kv = api._controller._kv
    count = 0

    # Store each major section as a separate core memory entry
    sections = {
        "identity:technical_interests": ("technical_interests", "Core technical interests and stack preferences"),
        "identity:dev_approach": ("development_approach", "Software development workflow and audit style"),
        "identity:ui_preferences": ("ui_preferences", "UI/UX design preferences and philosophy"),
        "identity:projects": ("projects", "Active and past software projects with architecture details"),
        "identity:hardware": ("hardware_interests", "PC hardware and performance interests"),
        "identity:gaming": ("gaming_interests", "Gaming preferences and BeamNG.drive challenge style"),
        "identity:opensource": ("open_source_approach", "How open-source projects are evaluated and used"),
        "identity:electronics": ("electronics_robotics", "Hardware/robotics projects and interaction philosophy"),
        "identity:documentation": ("documentation_philosophy", "Documentation standards and practices"),
        "identity:planning": ("project_planning", "Project planning methodology and terminology"),
        "identity:performance": ("performance_concerns", "Performance optimization priorities and focus areas"),
        "identity:reliability": ("reliability_concerns", "Reliability engineering philosophy and concerns"),
        "identity:security": ("security_concerns", "Security priorities and tooling"),
        "identity:feedback_style": ("feedback_style", "Preferred feedback and criticism style"),
        "identity:feature_creep": ("feature_creep_attitude", "Attitude toward feature creep and complexity"),
        "identity:tech_philosophy": ("technology_philosophy", "Overall technology philosophy and intersection focus"),
        "identity:common_requests": ("common_requests", "Frequent task types and requests across projects"),
        "identity:summary": ("summary", "High-level summary of working style and preferences"),
    }

    for key, (profile_key, description) in sections.items():
        content = USER_PROFILE.get(profile_key, {})
        if isinstance(content, (dict, list)):
            content_str = json.dumps(content, indent=2)
        else:
            content_str = str(content)

        # Store with high importance so it persists in CORE MEMORY
        kv.store(
            key=key,
            value=content_str,
            category="identity",
            importance=0.95,
        )
        count += 1

    # Also store the summary as a standalone easily-accessible entry
    kv.store(
        key="identity:user_summary",
        value=USER_PROFILE["summary"],
        category="identity",
        importance=0.99,
    )
    count += 1

    return count


def ensure_user_profile_in_memory(api) -> bool:
    """
    Ensure the user profile is loaded in the memory KV store.
    Call this at startup after get_mem() initializes.
    Returns True if profile was injected (or already present).
    """
    if api is None or api._controller is None or api._controller._kv is None:
        return False

    kv = api._controller._kv

    # Check if already present
    existing = kv.get("identity:user_summary")
    if existing and existing.get("value"):
        return True  # Already loaded

    # Inject the profile
    injected = inject_into_memory_api(api)
    return injected > 0