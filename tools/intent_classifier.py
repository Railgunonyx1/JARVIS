"""Intent classifier for JARVIS agent loop.

Classifies user requests into task types to determine appropriate
tool policies and prevent over-triggering filesystem/actions.
"""

from enum import Enum, auto


class TaskType(Enum):
    """Classification of user request types."""
    CONVERSATION = auto()      # Casual chat, greeting, questions
    INFORMATION_LOOKUP = auto()  # "what is", "who is", lookup queries
    ENGINEERING_TASK = auto()  # "create", "fix", "build", "analyze"
    AUDIT = auto()            # "audit", "inspect", "check"
    RESEARCH = auto()         # "search", "find", "investigate"
    SYSTEM_OPERATION = auto() # "restart", "status", "configure"


class IntentClassifier:
    """Classifies user intent to determine tool policies."""
    
    # Keywords/triggers for each task type
    _conversation_triggers = {"hello", "hi", "hey", "how are", "thanks", "ok"}
    _info_triggers = {"what is", "who is", "where is", "how", "explain", "define"}
    _engineering_triggers = {"create", "build", "fix", "analyze", "fix the", "repair"}
    _audit_triggers = {"audit", "inspect", "check", "review", "diagnostic"}
    _research_triggers = {"search", "find", "research", "look up", "google"}
    _system_triggers = {"restart", "status", "configure", "settings", "health"}
    
    _default_task = TaskType.CONVERSATION
    
    @classmethod
    def classify(cls, user_input: str) -> TaskType:
        """Classify the user's intent."""
        normalized = user_input.lower().strip()
        
        # Check for exact matches first
        if normalized in cls._conversation_triggers:
            return TaskType.CONVERSATION
        
        # Check prefix patterns
        for trigger in cls._info_triggers:
            if normalized.startswith(trigger):
                return TaskType.INFORMATION_LOOKUP
        
        for trigger in cls._engineering_triggers:
            if normalized.startswith(trigger) or trigger in normalized:
                return TaskType.ENGINEERING_TASK
        
        for trigger in cls._audit_triggers:
            if normalized.startswith(trigger) or trigger in normalized:
                return TaskType.AUDIT
        
        for trigger in cls._research_triggers:
            if normalized.startswith(trigger) or trigger in normalized:
                return TaskType.RESEARCH
        
        for trigger in cls._system_triggers:
            if normalized.startswith(trigger) or trigger in normalized:
                return TaskType.SYSTEM_OPERATION
        
        # Default: conversation
        return cls._default_task
    
    @classmethod
    def should_allow_tool(
        cls, 
        task_type: TaskType, 
        tool_name: str
    ) -> bool:
        """Check if a tool is allowed for the given task type."""
        
        # Audit task policies - read only
        if task_type == TaskType.AUDIT:
            audit_allowlist = {
                "filesystem.read": True,
                "shell.readonly": True,
                "pytest": True,
                "ruff": True,
                "dependency.audit": True,
            }
            return audit_allowlist.get(tool_name, False)
        
        # Engineering task policies
        if task_type == TaskType.ENGINEERING_TASK:
            eng_allowlist = {
                "filesystem.read": True,
                "filesystem.write": False,  # Requires explicit permission
                "shell.execute": True,
                "pytest": True,
                "pip_install": False,  # Never auto-install
                "pip_remove": False,
            }
            return eng_allowlist.get(tool_name, False)
        
        # Conversation task policies - very restricted
        if task_type == TaskType.CONVERSATION:
            conv_allowlist = {
                "respond": True,  # Just generate text response
            }
            return conv_allowlist.get(tool_name, False)
        
        # Information lookup - read-only tools
        if task_type == TaskType.INFORMATION_LOOKUP:
            info_allowlist = {
                "memory.search": True,
                "knowledge.search": True,
            }
            return info_allowlist.get(tool_name, False)
        
        # Research task policies - includes external world info tools
        if task_type == TaskType.RESEARCH:
            research_allowlist = {
                "memory.search": True,
                "knowledge.search": True,
                "world_monitor.search": True,  # External world info
                "world_monitor.get_sources": True,
                "world_monitor.get_alerts": True,  # Situational alerts
            }
            return research_allowlist.get(tool_name, False)
        
        # Default: deny unknown tool for unknown task type
        return False
    
    @classmethod
    def get_response_mode(cls, task_type: TaskType) -> str:
        """Get the appropriate response mode for a task type."""
        modes = {
            TaskType.CONVERSATION: "conversational",
            TaskType.INFORMATION_LOOKUP: "informational",
            TaskType.ENGINEERING_TASK: "action_required",
            TaskType.AUDIT: "evidence_based",
            TaskType.RESEARCH: "summary",
            TaskType.SYSTEM_OPERATION: "status_report",
        }
        return modes.get(task_type, "conversational")