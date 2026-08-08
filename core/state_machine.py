"""Kernel + Service State Machines with transition validation.

KernelState — top-level JARVIS lifecycle (BOOTING → STARTING → READY → ...)
ServiceState — per-service lifecycle (CREATED → INITIALIZING → RUNNING → ...)
"""
from enum import Enum, auto


class KernelState(Enum):
    BOOTING = auto()
    STARTING = auto()
    READY = auto()
    LISTENING = auto()
    THINKING = auto()
    EXECUTING = auto()
    SPEAKING = auto()
    IDLE = auto()
    SHUTDOWN = auto()
    FAILED = auto()

    def can_transition_to(self, target: "KernelState") -> bool:
        transitions = {
            KernelState.BOOTING: {KernelState.STARTING, KernelState.FAILED},
            KernelState.STARTING: {KernelState.READY, KernelState.FAILED},
            KernelState.READY: {KernelState.LISTENING, KernelState.THINKING, KernelState.IDLE, KernelState.SHUTDOWN, KernelState.FAILED},
            KernelState.LISTENING: {KernelState.THINKING, KernelState.READY, KernelState.IDLE, KernelState.SHUTDOWN, KernelState.FAILED},
            KernelState.THINKING: {KernelState.EXECUTING, KernelState.SPEAKING, KernelState.READY, KernelState.FAILED},
            KernelState.EXECUTING: {KernelState.THINKING, KernelState.SPEAKING, KernelState.READY, KernelState.FAILED},
            KernelState.SPEAKING: {KernelState.LISTENING, KernelState.IDLE, KernelState.READY, KernelState.SHUTDOWN, KernelState.FAILED},
            KernelState.IDLE: {KernelState.LISTENING, KernelState.SHUTDOWN, KernelState.FAILED},
            KernelState.SHUTDOWN: set(),
            KernelState.FAILED: {KernelState.BOOTING},
        }
        return target in transitions.get(self, set())


class ServiceState(Enum):
    CREATED = auto()
    INITIALIZING = auto()
    RUNNING = auto()
    DEGRADED = auto()
    STOPPING = auto()
    STOPPED = auto()
    FAILED = auto()

    def can_transition_to(self, target: "ServiceState") -> bool:
        transitions = {
            ServiceState.CREATED: {ServiceState.INITIALIZING, ServiceState.FAILED},
            ServiceState.INITIALIZING: {ServiceState.RUNNING, ServiceState.FAILED, ServiceState.STOPPING},
            ServiceState.RUNNING: {ServiceState.DEGRADED, ServiceState.STOPPING, ServiceState.FAILED},
            ServiceState.DEGRADED: {ServiceState.RUNNING, ServiceState.STOPPING, ServiceState.FAILED},
            ServiceState.STOPPING: {ServiceState.STOPPED, ServiceState.FAILED},
            ServiceState.STOPPED: {ServiceState.CREATED},
            ServiceState.FAILED: {ServiceState.CREATED},
        }
        return target in transitions.get(self, set())
