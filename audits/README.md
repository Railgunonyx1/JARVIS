# JARVIS MK-X — Audit Reports Index

All audit artifacts are consolidated here so before/after snapshots and
historical reports live in one place.

## Current reports

| Report | Description |
|---|---|
| [`audit_before.md`](audit_before.md) | Full pre-audit snapshot: tests, ruff, bandit, deps, mypy, GitHub research, findings + fixes. |
| [`audit_after.md`](audit_after.md) | Post-fix verification: bandit HIGH cleared, retry/jitter improvements, remaining backlog. |

## Raw artifacts

| File | Description |
|---|---|
| `bandit_before.json` | Bandit scan of active tree before fixes (135 findings). |
| `bandit_after.json` | Bandit scan of active tree after fixes (131 findings, 0 HIGH; B607 resolved). |
| `pip-audit_before.txt` | Dependency vulnerability scan — no known vulnerabilities. |

## Historical reports (pre-existing, copied from `audit/`)

| File | Description |
|---|---|
| `history/01_system_latency_map.md` | Latency map across subsystems. |
| `history/02_hotspots.md` | Performance hotspots. |
| `history/03_quick_wins.md` | Quick-win optimizations. |
| `history/04_architecture_recommendations.md` | Architecture guidance. |
| `history/05_metrics_baseline.md` | Metrics baseline. |
| `history/06_full_technical_audit.md` | Full technical audit. |
| `history/08_phase0_baseline.md` | Phase-0 baseline. |
| `history/comprehensive_audit_report.md` | Comprehensive audit report. |

## How the audit was run

```
pytest -q tests
python -m ruff check <tree>
python -m bandit -r core security tools daemon memory providers runtime systems workflows cli -f json -o audits/bandit_*.json
python -m pip_audit -r requirements.txt
python -m pip check
```
