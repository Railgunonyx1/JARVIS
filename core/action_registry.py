"""Action Registry — replaces the 30+ branch if/elif chain in _handle_action.

Each action is a class registered by name. Supports lazy import of handlers.
"""
import asyncio
import logging
from typing import Any, Callable, Dict, Optional, Type

logger = logging.getLogger("jarvis.action_registry")


class ActionHandler:
    """Base class for action handlers. Override handle() in subclasses."""

    async def handle(self, intent, text: str, api_keys: dict = None) -> Optional[str]:
        raise NotImplementedError


class ActionRegistry:
    """Maps intent names to handler classes. Lazy-imports on first use."""

    def __init__(self):
        self._handlers: Dict[str, Type[ActionHandler]] = {}
        self._instances: Dict[str, ActionHandler] = {}
        self._lazy_handlers: Dict[str, Callable] = {}

    def register(self, name: str, handler_cls: Type[ActionHandler]):
        self._handlers[name] = handler_cls

    def register_lazy(self, name: str, import_fn: Callable):
        """Register a lazy-imported handler."""
        self._lazy_handlers[name] = import_fn

    def get_handler(self, name: str) -> Optional[ActionHandler]:
        if name in self._handlers and name not in self._instances:
            self._instances[name] = self._handlers[name]()
        if name in self._instances:
            return self._instances[name]
        if name in self._lazy_handlers:
            try:
                handler_cls = self._lazy_handlers[name]()
                if handler_cls:
                    if isinstance(handler_cls, type) and issubclass(handler_cls, ActionHandler):
                        self._instances[name] = handler_cls()
                        return self._instances[name]
                    self._instances[name] = handler_cls
                    return self._instances[name]
            except Exception as e:
                logger.debug("Failed to lazy-load action '%s': %s", name, e)
        return None

    async def execute(self, intent, text: str,
                      api_keys: dict = None) -> Optional[str]:
        handler = self.get_handler(intent.name)
        if handler is None:
            return None
        return await handler.handle(intent, text, api_keys=api_keys)

    def get_names(self) -> list[str]:
        return sorted(set(self._handlers.keys()) | set(self._lazy_handlers.keys()))
