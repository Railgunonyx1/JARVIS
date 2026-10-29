#!/usr/bin/env bash
set -euo pipefail

# One-command reconciliation + verification for the local audit checkpoint.
# Runs both the focused modules and the full combined desktop suites with
# DeprecationWarning treated as an error after caches are cleared.
#
# Caveat: this reruns the same suites that generated the recorded evidence.
# It improves confidence in the working tree and note, but it is not a
# substitute for a clean checkout of the exact committed SHA.

cd "$(dirname "$0")/.."

echo "=== cleaning caches ==="
rm -rf \
  dynamic-island/__pycache__ \
  dynamic-island/tests/__pycache__ \
  dynamic-island/app/__pycache__ \
  dynamic-island/app/ui/__pycache__ \
  dynamic-island/app/integration/__pycache__ \
  dynamic-island/app/desktop/__pycache__ \
  tests/__pycache__ \
  tests/desktop/__pycache__ \
  core/__pycache__ \
  core/agent/__pycache__ \
  packaging/__pycache__ \
  tmp/__pycache__

echo "=== focused reconciliation modules ==="
QT_QPA_PLATFORM=offscreen python -m pytest \
  dynamic-island/tests/desktop/test_island.py \
  dynamic-island/tests/desktop/test_approval_boundary.py \
  tests/desktop/test_island.py \
  -q --import-mode=importlib -W error::DeprecationWarning

echo "=== full combined desktop suites ==="
QT_QPA_PLATFORM=offscreen python -m pytest \
  dynamic-island/tests/desktop/ \
  tests/desktop/ \
  -q --import-mode=importlib -W error::DeprecationWarning

