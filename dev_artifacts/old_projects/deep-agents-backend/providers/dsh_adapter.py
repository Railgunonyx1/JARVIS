"""DeepSeek Harness Adapter — bridge between JARVIS and DSH runtime.

This module provides:
1. DSHRuntimeManager - manages DSH subprocess lifecycle
2. DSHAgentClient - sends tasks to DSH agent via JSON-RPC
3. DSHPluginRegistry - maps JARVIS tools/skills to DSH plugins

Usage (when DSH is available):
    from providers.dsh_adapter import DSHRuntimeManager
    
    dsh = DSHRuntimeManager()
    dsh.start()
    result = dsh.run_task("Fix the authentication bug")
    dsh.stop()

Architecture:
    JARVIS CLI → DSHAdapter → DSH Runtime (Node.js subprocess)
                              ↓
                         JSON-RPC over stdio
                              ↓
                         Cordis Plugin System
                              ↓
                    ┌─────────┴─────────┐
                    │                   │
               DSH Plugins         JARVIS Plugins
               (tools, models)     (memory, verify)
"""

from __future__ import annotations

import json
import logging
import subprocess
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger("jarvis.dsh")

# DSH configuration paths
DSH_ROOT = Path(__file__).parent.parent / "migration" / "dsh"
DSH_RUNTIME = DSH_ROOT / "node_modules" / ".bin" / "dsh"
DSH_CORDIS_CONFIG = DSH_ROOT / "examples" / "jsonrpc-agent" / "cordis.yml"


@dataclass
class DSHConfig:
    """Configuration for DSH runtime."""
    provider: str = "ollama"
    model: str = "qwen2.5:3b"
    max_tokens: int = 4096
    cordis_config: str | None = None
    timeout_seconds: float = 300.0
    env_overrides: dict[str, str] = field(default_factory=dict)


@dataclass
class DSHResult:
    """Result from a DSH agent task."""
    success: bool
    response: str
    session_id: str = ""
    finish_reason: str = ""
    events: list[dict] = field(default_factory=list)
    error: str = ""


class DSHRuntimeManager:
    """Manages the DSH runtime subprocess.
    
    The runtime is a Node.js process that communicates via JSON-RPC over stdio.
    It loads the Cordis plugin system and provides agent capabilities.
    """
    
    def __init__(self, config: DSHConfig | None = None):
        self.config = config or DSHConfig()
        self._process: subprocess.Popen | None = None
        self._reader_thread: threading.Thread | None = None
        self._lock = threading.Lock()
        self._available = False
        self._request_id = 0
        self._pending: dict[int, threading.Event] = {}
        self._responses: dict[int, dict] = {}
    
    @property
    def is_available(self) -> bool:
        """Check if DSH runtime is available and running."""
        return self._available and self._process is not None
    
    def start(self) -> bool:
        """Start the DSH runtime subprocess.
        
        Returns:
            True if started successfully, False otherwise.
        """
        if self._available:
            return True
        
        # Check if DSH is installed
        if not DSH_RUNTIME.exists() and not self._find_dsh_binary():
            logger.warning("DSH runtime not found at %s", DSH_RUNTIME)
            return False
        
        try:
            # Build environment
            env = {
                **dict(__import__('os').environ),
                "NODE_ENV": "production",
                **self.config.env_overrides,
            }
            
            # Build command
            cmd = [str(DSH_RUNTIME), "--headless"]
            if self.config.cordis_config:
                cmd.extend(["--cordis", self.config.cordis_config])
            
            # Start process
            self._process = subprocess.Popen(
                cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=env,
                text=True,
                bufsize=1,
            )
            
            # Start reader thread
            self._reader_thread = threading.Thread(
                target=self._read_loop,
                daemon=True,
                name="dsh-reader",
            )
            self._reader_thread.start()
            
            # Wait for ready signal
            if self._wait_for_ready(timeout=10.0):
                self._available = True
                logger.info("DSH runtime started (pid=%s)", self._process.pid)
                return True
            else:
                self.stop()
                return False
                
        except Exception as e:
            logger.error("Failed to start DSH runtime: %s", e)
            self.stop()
            return False
    
    def stop(self) -> None:
        """Stop the DSH runtime subprocess."""
        self._available = False
        if self._process:
            try:
                self._process.terminate()
                self._process.wait(timeout=5.0)
            except Exception:
                try:
                    self._process.kill()
                except Exception:
                    pass
            self._process = None
        logger.info("DSH runtime stopped")
    
    def run_task(self, task: str, timeout: float | None = None) -> DSHResult:
        """Run a task through the DSH agent.
        
        Args:
            task: The task description/prompt.
            timeout: Timeout in seconds (uses config default if None).
            
        Returns:
            DSHResult with the agent's response.
        """
        if not self.is_available:
            return DSHResult(
                success=False,
                response="",
                error="DSH runtime not available",
            )
        
        timeout = timeout or self.config.timeout_seconds
        
        try:
            # Send task via JSON-RPC
            request_id = self._next_request_id()
            request = {
                "jsonrpc": "2.0",
                "id": request_id,
                "method": "agent/run",
                "params": {
                    "prompt": task,
                    "model": self.config.model,
                    "max_tokens": self.config.max_tokens,
                },
            }
            
            # Wait for response
            event = threading.Event()
            self._pending[request_id] = event
            
            self._send_request(request)
            
            if not event.wait(timeout=timeout):
                return DSHResult(
                    success=False,
                    response="",
                    error=f"DSH task timed out after {timeout}s",
                )
            
            response = self._responses.pop(request_id, {})
            
            if "error" in response:
                return DSHResult(
                    success=False,
                    response="",
                    error=response["error"].get("message", "Unknown error"),
                )
            
            result = response.get("result", {})
            return DSHResult(
                success=True,
                response=result.get("response", ""),
                session_id=result.get("session_id", ""),
                finish_reason=result.get("finish_reason", ""),
                events=result.get("events", []),
            )
            
        except Exception as e:
            return DSHResult(
                success=False,
                response="",
                error=str(e),
            )
    
    def _find_dsh_binary(self) -> bool:
        """Try to find DSH binary in common locations."""
        import shutil
        dsh_path = shutil.which("dsh")
        if dsh_path:
            DSH_RUNTIME.parent.mkdir(parents=True, exist_ok=True)
            DSH_RUNTIME.symlink_to(dsh_path)
            return True
        return False
    
    def _wait_for_ready(self, timeout: float) -> bool:
        """Wait for DSH runtime to signal ready."""
        deadline = time.time() + timeout
        while time.time() < deadline:
            if self._process and self._process.poll() is not None:
                return False
            time.sleep(0.1)
        return self._process is not None and self._process.poll() is None
    
    def _next_request_id(self) -> int:
        """Get next unique request ID."""
        with self._lock:
            self._request_id += 1
            return self._request_id
    
    def _send_request(self, request: dict) -> None:
        """Send a JSON-RPC request to DSH."""
        if self._process and self._process.stdin:
            line = json.dumps(request) + "\n"
            self._process.stdin.write(line)
            self._process.stdin.flush()
    
    def _read_loop(self) -> None:
        """Read responses from DSH in background thread."""
        if not self._process or not self._process.stdout:
            return
        
        try:
            for line in self._process.stdout:
                line = line.strip()
                if not line:
                    continue
                
                try:
                    response = json.loads(line)
                    request_id = response.get("id")
                    
                    if request_id and request_id in self._pending:
                        self._responses[request_id] = response
                        self._pending[request_id].set()
                    else:
                        # Notification or unknown response
                        logger.debug("DSH notification: %s", response)
                        
                except json.JSONDecodeError:
                    logger.warning("Invalid JSON from DSH: %s", line[:100])
                    
        except Exception as e:
            logger.error("DSH reader error: %s", e)
        finally:
            self._available = False


class DSHAgentClient:
    """High-level client for interacting with DSH agent.
    
    Wraps DSHRuntimeManager with JARVIS-specific conveniences.
    """
    
    def __init__(self, runtime: DSHRuntimeManager | None = None):
        self._runtime = runtime or DSHRuntimeManager()
        self._initialized = False
    
    def initialize(self) -> bool:
        """Initialize the DSH connection."""
        if self._initialized:
            return True
        
        if self._runtime.start():
            self._initialized = True
            return True
        return False
    
    def execute(self, task: str, **kwargs) -> DSHResult:
        """Execute a task through DSH.
        
        This is the main entry point for JARVIS to use DSH capabilities.
        """
        if not self._initialized:
            if not self.initialize():
                return DSHResult(
                    success=False,
                    response="",
                    error="DSH initialization failed",
                )
        
        return self._runtime.run_task(task, **kwargs)
    
    def shutdown(self) -> None:
        """Shutdown the DSH connection."""
        self._runtime.stop()
        self._initialized = False


# Global DSH client instance
_dsh_client: DSHAgentClient | None = None


def get_dsh_client() -> DSHAgentClient:
    """Get the global DSH client instance."""
    global _dsh_client
    if _dsh_client is None:
        _dsh_client = DSHAgentClient()
    return _dsh_client


def is_dsh_available() -> bool:
    """Check if DSH is available and ready."""
    return get_dsh_client().initialize()
