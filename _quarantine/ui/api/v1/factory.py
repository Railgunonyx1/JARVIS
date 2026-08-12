"""API v1 factory — wires APIs to kernel services within the DI container."""
from api.v1 import CapabilityAPI, EventAPI, MemoryAPI, SecurityAPI


def create_memory_api(container) -> MemoryAPI:
    from memory.store import MemoryStore
    store = container.resolve(MemoryStore) if container.is_registered(MemoryStore) else None
    vector = None
    try:
        from memory.vector_store import VectorMemoryStore
        vector = container.resolve(VectorMemoryStore) if container.is_registered(VectorMemoryStore) else None
    except Exception:
        pass
    return MemoryAPI(memory_store=store, vector_memory=vector)


def create_event_api(container) -> EventAPI:
    from systems.event_bus import EventBus
    bus = container.resolve(EventBus) if container.is_registered(EventBus) else None
    return EventAPI(event_bus=bus)


def create_capability_api(container) -> CapabilityAPI:
    from core.action_registry import ActionRegistry
    registry = container.resolve(ActionRegistry) if container.is_registered(ActionRegistry) else None
    return CapabilityAPI(action_registry=registry)


def create_security_api(container) -> SecurityAPI:
    return SecurityAPI()


def wire_apis(container):
    """Register all API v1 instances in the container."""
    container.register_instance(MemoryAPI, create_memory_api(container))
    container.register_instance(EventAPI, create_event_api(container))
    container.register_instance(CapabilityAPI, create_capability_api(container))
    container.register_instance(SecurityAPI, create_security_api(container))
