# Security Policy — JARVIS MK-X

JARVIS MK-X takes execution safety and system integrity seriously. Because the agent executes shell commands, automates web browsers, and manages LLM provider interactions, a multi-tier defense-in-depth model is baked directly into the kernel.

---

## 🛡️ Security Architecture & Invariants

JARVIS MK-X is governed by strict architectural security invariants:

1. **Single Tool Execution Boundary**:
   Every tool execution—whether invoked by the core Agent Loop, MCP (Model Context Protocol), ACP (Agent Client Protocol), or Codex adapters—MUST pass through `core.agent.tool_service.ToolExecutionService`. Direct executor instantiation outside the single boundary is statically forbidden and enforced by AST-based invariant tests (`tests/test_architecture_invariants.py`).

2. **Fail-Closed Permission Engine**:
   Tools are declaratively classified with risk levels (`LOW`, `MEDIUM`, `HIGH`, `CRITICAL`) and destructiveness flags (`is_destructive`). In `Controlled` and `Smart` modes, any action that mutates the filesystem, executes arbitrary scripts, or accesses external state requires explicit operator consent. If consent cannot be prompted or obtained, the engine fails closed (`DENIED`).

3. **Sensitive Web Origin Shield (Orbit / J-Browser)**:
   The browser intelligence layer intercepts all navigation and interaction requests. Sensitive origins (banking, webmail, cloud provider consoles, identity providers) are flagged by `security.sensitive_sites` and require elevated operator authorization before navigation or form interaction can proceed. Loopback and private IP browsing are denied by default (`jbrowser.network.BrowserNetworkPolicy`).

4. **Automated Secret Redaction**:
   All outputs from tool executions, shell processes, and streaming telemetry pass through automated secret redaction before reaching the LLM context, terminal viewport, or persistent event log (`security.redaction`).

5. **Post-Execution Verification Gate**:
   Mutating actions (file writes, patches, commits) are verified against the physical filesystem and environment state before a task is considered completed (`OBSERVING → EXECUTING → VERIFYING → RECOVERING`).

---

## 📦 Supported Versions

| Version | Supported | Security Maintenance |
| :--- | :---: | :--- |
| **JARVIS MK-X (Current)** |  | Active security patches & automated regression testing |
| **JARVIS MK-IX (Legacy)** |  | Quarantined under `_quarantine/` |

---

## 🚨 Reporting a Vulnerability

If you discover a security vulnerability within JARVIS MK-X, please **do not open a public issue**. Instead, follow responsible disclosure:

1. Email the maintainer directly at **aayanmemon1111@gmail.com** with the subject `[SECURITY VULNERABILITY] JARVIS MK-X`.
2. Provide a detailed description including:
   - Affected subsystem (e.g., `ToolExecutionService`, `jbrowser-bridge`, `permissions.py`).
   - Proof of Concept (PoC) or reproduction steps.
   - Potential impact and risk scenario.
   - Any suggested mitigations.
3. You will receive an acknowledgment within 48 hours, along with a timeline for patch development and disclosure.
