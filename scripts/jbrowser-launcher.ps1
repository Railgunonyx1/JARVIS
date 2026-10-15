param(
    [string]$Backend = "echo",
    [switch]$FirstRun
)
# Launcher for J-Browser (real Chrome + JARVIS layer).
#
# What it does:
#   1. Starts the JARVIS bridge server (jbrowser-bridge/server.py) if not
#      already listening on 127.0.0.1:8170.
#   2. Opens your normal Google Chrome (all your extensions intact) onto the
#      JARVIS new-tab home.
#
# First-run note: branded Chrome 137+ removed the --load-extension flag, so the
# JARVIS extension is loaded ONCE via chrome://extensions -> Developer mode ->
# "Load unpacked" -> select  <repo>\extensions\jbrowser\  . After that it
# persists across launches. Use -FirstRun to open that page for you.

$ErrorActionPreference = "Stop"

# --- paths -----------------------------------------------------------------
$ScriptsDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$Root = Split-Path -Parent $ScriptsDir
$Python = Join-Path $Root "venv\Scripts\python.exe"
$Server = Join-Path $Root "jbrowser-bridge\server.py"
$ExtDir = Join-Path $Root "extensions\jbrowser"
$BridgeUrl = "http://127.0.0.1:8170/status"
$BridgePort = 8170

# Chrome executable (common install locations)
$ChromeCandidates = @(
    "$env:ProgramFiles\Google\Chrome\Application\chrome.exe",
    "${env:ProgramFiles(x86)}\Google\Chrome\Application\chrome.exe",
    "$env:LOCALAPPDATA\Google\Chrome\Application\chrome.exe"
)
$Chrome = $ChromeCandidates | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1

# --- validate --------------------------------------------------------------
if (-not (Test-Path -LiteralPath $Python)) {
    Write-Host "ERROR: venv python not found at $Python" -ForegroundColor Red
    Read-Host "Press Enter to close"
    exit 1
}
if (-not $Chrome) {
    Write-Host "ERROR: Google Chrome not found." -ForegroundColor Red
    Read-Host "Press Enter to close"
    exit 1
}

Write-Host "J-Browser  (real Chrome + JARVIS)" -ForegroundColor Cyan
Write-Host "================================"

# --- stage 1: bridge -------------------------------------------------------
$bridgeUp = $false
try {
    $r = Invoke-RestMethod -Uri $BridgeUrl -TimeoutSec 2
    $bridgeUp = $true
    Write-Host ("Bridge: already running  (kernel=" + $r.kernel + ")")
} catch {
    $bridgeUp = $false
}

if (-not $bridgeUp) {
    Write-Host ("Bridge: starting ($Backend backend) ...")
    Start-Process -FilePath $Python -ArgumentList @($Server, "--backend", $Backend) -WindowStyle Minimized
    $ok = $false
    for ($i = 0; $i -lt 20; $i++) {
        Start-Sleep -Milliseconds 400
        try {
            $r = Invoke-RestMethod -Uri $BridgeUrl -TimeoutSec 1
            if ($r.ok) { $ok = $true; break }
        } catch { }
    }
    Write-Host ("Bridge: " + $(if ($ok) { "up (kernel=" + $r.kernel + ")" } else { "still starting (you can browse anyway)" }))
}

# --- stage 2: Chrome -------------------------------------------------------
$chromeArgs = @("--new-window")
if ($FirstRun) {
    # open the extension page so the one-time "Load unpacked" is one click,
    # then open the JARVIS home
    Start-Process -FilePath $Chrome -ArgumentList @("--new-window", "chrome://extensions/")
    Start-Sleep -Milliseconds 800
    $chromeArgs = @("--new-window", "chrome://newtab")
} else {
    $chromeArgs = @("--new-window", "chrome://newtab")
}

Start-Process -FilePath $Chrome -ArgumentList $chromeArgs
Write-Host ("Chrome: opened ($($Chrome))")

if ($FirstRun) {
    Write-Host ""
    Write-Host "FIRST RUN" -ForegroundColor Yellow
    Write-Host "On the extensions page that opened:" -ForegroundColor Yellow
    Write-Host "  1. Enable  Developer mode  (top-right)"
    Write-Host "  2. Click  Load unpacked"
    Write-Host ("  3. Select  $ExtDir")
    Write-Host "The JARVIS extension will then persist across launches." -ForegroundColor Yellow
}

Write-Host ""
Write-Host "Bridge listens on 127.0.0.1:8170 (use --backend kernel once wired)." -ForegroundColor DarkGray
