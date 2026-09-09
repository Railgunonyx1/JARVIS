# JARVIS Orbit - wait-window.ps1
# Launches the Electron browser and waits until its main window exists
# (or the process exits), then returns.
#  - WorkDir comes from cmd's %~dp0 which ends with a backslash; normalize it
#    or Start-Process throws DirectoryNotFoundException and nothing launches.
#  - Fail fast (exit 1) so the launcher reports the error instead of exiting 0
#    with no browser.
#  - Exit 0 when the window is up OR the process ended (single-instance
#    handoff), 1 on launch failure.

param(
    [string]$ElectronPath,
    [string]$WorkDir
)

if (-not $ElectronPath -or -not (Test-Path -LiteralPath $ElectronPath)) { exit 1 }
$WorkDir = ($WorkDir -replace '"', '').TrimEnd('\')
if (-not $WorkDir -or -not (Test-Path -LiteralPath $WorkDir)) { exit 1 }

try {
    $p = Start-Process -FilePath $ElectronPath -ArgumentList '"."' -WorkingDirectory $WorkDir -PassThru
} catch {
    [Console]::Error.WriteLine("Failed to launch Electron: $_")
    exit 1
}
if (-not $p) { exit 1 }

$t = 0
while ($t -lt 100) {
    Start-Sleep -Milliseconds 300
    $t++
    $proc = Get-Process -Id $p.Id -ErrorAction SilentlyContinue
    if ($proc -and $proc.MainWindowHandle -ne 0) { break }
    if (-not $proc) { break }
}
exit 0