# JARVIS Orbit - wait-window.ps1
# Launches the Electron browser and waits until its main window exists
# (or the process exits), then returns. Bounded: never waits more than
# ~30 seconds. Exit 0 when the window is up OR the process ended
# (single-instance handoff), 1 when Electron is missing.

param(
    [string]$ElectronPath,
    [string]$WorkDir
)

if (-not (Test-Path $ElectronPath)) { exit 1 }

$p = Start-Process -FilePath $ElectronPath -ArgumentList '"."' -WorkingDirectory $WorkDir -PassThru
$t = 0
while ($t -lt 100) {
    Start-Sleep -Milliseconds 300
    $t++
    $proc = Get-Process -Id $p.Id -ErrorAction SilentlyContinue
    if ($proc -and $proc.MainWindowHandle -ne 0) { break }
    if (-not $proc) { break }
}
exit 0
