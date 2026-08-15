# verify.ps1 — JARVIS MK-X quality gate.
#
# Runs the same checks CI would run, in dependency order:
#   1. Ruff lint (E/F/W/I/UP/B/PLW, line-length 120)
#   2. Full test suite (pytest, includes tests/test_imports.py guard suite)
#
# Usage:
#   powershell -ExecutionPolicy Bypass -File verify.ps1
#   powershell -ExecutionPolicy Bypass -File verify.ps1 -SkipLint
#   powershell -ExecutionPolicy Bypass -File verify.ps1 -SkipTests
#
# Exits 0 on success, 1 on any failure.

param(
    [switch]$SkipLint,
    [switch]$SkipTests
)

$ErrorActionPreference = "Stop"
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $here

$fail = 0

function Report-Title($title) {
    Write-Host ""
    Write-Host ("=" * 60) -ForegroundColor Cyan
    Write-Host "  $title" -ForegroundColor Cyan
    Write-Host ("=" * 60) -ForegroundColor Cyan
}

function Report-Step($name, $ok) {
    if ($ok) {
        Write-Host "  [PASS] $name" -ForegroundColor Green
    } else {
        Write-Host "  [FAIL] $name" -ForegroundColor Red
        $script:fail = 1
    }
}

# Locate a python. Prefer the venv, fall back to PATH.
$py = "python"
foreach ($cand in @("venv\Scripts\python.exe", ".venv\Scripts\python.exe")) {
    if (Test-Path $cand) { $py = (Resolve-Path $cand).Path; break }
}

Write-Host "JARVIS MK-X verify gate"
Write-Host "  python:  $py"
Write-Host "  cwd:     $here"
Write-Host "  skip:    lint=$SkipLint tests=$SkipTests"

if (-not $SkipLint) {
    Report-Title "1. RUFF LINT"
    $lintOut = & $py -m ruff check . 2>&1
    if ($LASTEXITCODE -eq 0) {
        Report-Step "ruff check" $true
    } else {
        $lintOut | ForEach-Object { Write-Host "    $_" -ForegroundColor Yellow }
        Report-Step "ruff check" $false
    }
}

if (-not $SkipTests) {
    Report-Title "2. TEST SUITE"
    $testOut = & $py -m pytest tests/ -q 2>&1
    if ($LASTEXITCODE -eq 0) {
        $testOut | Select-Object -Last 3 | ForEach-Object { Write-Host "    $_" }
        Report-Step "pytest (full suite)" $true
    } else {
        $testOut | Select-Object -Last 15 | ForEach-Object { Write-Host "    $_" -ForegroundColor Yellow }
        Report-Step "pytest (full suite)" $false
    }
}

Write-Host ""
Write-Host ("=" * 60)
if ($fail -eq 0) {
    Write-Host "  VERIFY OK" -ForegroundColor Green
} else {
    Write-Host "  VERIFY FAILED" -ForegroundColor Red
}
Write-Host ("=" * 60)

exit $fail
