# JARVIS Orbit - wait-window.ps1
# Launches the Electron browser and waits until its main window exists
# (or the process exits), then returns.
#  - WorkDir comes from cmd's %~dp0 which ends with a backslash; normalize it
#    or Start-Process throws DirectoryNotFoundException and nothing launches.
#  - Fail fast (exit 1) so failures are recorded instead of exiting 0 quietly.
#  - Exit 0 when the window is up OR the process ended (single-instance
#    handoff), 1 on launch failure. Errors are appended to -LogPath so the
#    console can close immediately at launch (browser runs detached).
param(
    [string]$ElectronPath,
    [string]$WorkDir,
    [string]$LogPath = ""
)

if (-not $LogPath) { $LogPath = Join-Path $env:TEMP "orbit-launch-error.log" }

function Log-Error([string]$msg) {
    try {
        Add-Content -LiteralPath $LogPath -Value ("[{0}] {1}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $msg) -Encoding UTF8
    } catch {}
    [Console]::Error.WriteLine($msg)
}

if (-not $ElectronPath -or -not (Test-Path -LiteralPath $ElectronPath)) {
    Log-Error "Electron not found: $ElectronPath"
    exit 1
}
$WorkDir = ($WorkDir -replace '"', '').TrimEnd('\')
if (-not $WorkDir -or -not (Test-Path -LiteralPath $WorkDir)) {
    Log-Error "WorkDir not found: $WorkDir"
    exit 1
}

try {
    $p = Start-Process -FilePath $ElectronPath -ArgumentList '"."' -WorkingDirectory $WorkDir -PassThru
} catch {
    Log-Error "Failed to launch Electron: $_"
    exit 1
}
if (-not $p) {
    Log-Error "Start-Process returned no process handle"
    exit 1
}

$t = 0
while ($t -lt 100) {
    Start-Sleep -Milliseconds 300
    $t++
    $proc = Get-Process -Id $p.Id -ErrorAction SilentlyContinue
    if ($proc -and $proc.MainWindowHandle -ne 0) { break }
    if (-not $proc) { break }
}
exit 0