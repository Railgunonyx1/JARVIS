# JARVIS MK-X — Audit & Architecture Reports Index

All audit artifacts, architectural assessments, and optimization ledgers are consolidated here for complete visibility and historical traceability.

## Subsystem Audits & Verification

| Report | Description |
|---|---|
| [`AUDIT-FINAL-REPORT.md`](AUDIT-FINAL-REPORT.md) | Comprehensive system audit across all subsystems, tool boundary, and performance. |
| [`AUDIT_SUMMARY.md`](AUDIT_SUMMARY.md) | High-level executive audit summary and invariant compliance matrix. |
| [`REVIEW-report.md`](REVIEW-report.md) | Detailed code review, security posture, and refactoring checklist. |
| [`VERIFIED-REPORT.md`](VERIFIED-REPORT.md) | Formal verification pass on the agent loop, verification engine, and memory stores. |
| [`JARVIS_OPTIMIZATION.md`](JARVIS_OPTIMIZATION.md) | Runtime latency, TTFT, and memory allocation optimization roadmap. |
| [`JARVIS_OPTIMIZATION_REPORT.md`](JARVIS_OPTIMIZATION_REPORT.md) | Benchmark data, before/after timing comparisons, and caching verification. |
| [`audit_before.md`](audit_before.md) | Pre-audit baseline: tests, Ruff, Bandit, dependencies, and AST scan. |
| [`audit_after.md`](audit_after.md) | Post-fix verification: Bandit HIGH vulnerabilities cleared, retry/jitter improvements. |

## Raw Security Artifacts

| File | Description |
|---|---|
| `bandit_before.json` | Bandit AST scan of active codebase before hardening (135 findings). |
| `bandit_after.json` | Bandit AST scan after fixes (131 findings, 0 HIGH; B607 resolved). |
| `pip-audit_before.txt` | Dependency vulnerability scan — zero known vulnerabilities. |

## Historical Reports

| File | Description |
|---|---|
| `history/01_system_latency_map.md` | Latency map across core execution paths. |
| `history/02_hotspots.md` | Performance hotspots and CPU bottlenecks. |
| `history/03_quick_wins.md` | Quick-win optimizations implemented in Phase A. |
| `history/04_architecture_recommendations.md` | Architectural guidance for multi-agent scaling. |
| `history/05_metrics_baseline.md` | Metrics baseline and TTFT tracking. |
| `history/06_full_technical_audit.md` | Full technical subsystem audit. |
| `history/08_phase0_baseline.md` | Phase-0 initial baseline. |
| `history/comprehensive_audit_report.md` | Historical comprehensive audit report. |

## Audit Reproduction Suite

```bash
# Test suite execution
pytest -q tests

# Static analysis and linting
ruff check .

# Bandit AST security scanner
bandit -r core security tools daemon memory providers runtime cli -f json -o audits/bandit_report.json

# Dependency vulnerability verification
pip-audit -r requirements.txt
```
