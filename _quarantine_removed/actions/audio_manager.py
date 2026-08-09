"""Audio Manager — switch devices, volume control for JARVIS MK-X."""

import subprocess
import logging

logger = logging.getLogger("jarvis.actions.audio_manager")


def audio_action(action: str, parameters: dict, **kwargs) -> str:
    handlers = {
        "devices": _list_devices,
        "set_output": _set_output_device,
        "set_input": _set_input_device,
        "volume": _set_volume,
        "get_volume": _get_volume,
        "mute": _mute,
        "unmute": _unmute,
        "test_speakers": _test_speakers,
    }
    handler = handlers.get(action)
    if not handler:
        return f"Unknown audio action: {action}"
    try:
        return handler(parameters)
    except Exception as e:
        logger.error("Audio action '%s' failed: %s", action, e)
        return f"Audio operation failed: {e}"


def _ps(cmd: str) -> str:
    try:
        r = subprocess.run(
            ["powershell", "-NoProfile", "-Command", cmd],
            capture_output=True, text=True, timeout=15,
        )
        return r.stdout.strip()
    except Exception as e:
        return f"Error: {e}"


def _list_devices(params: dict) -> str:
    kind = params.get("kind", "all")
    if kind == "output":
        out = _ps("Get-AudioDevice -List | Where-Object {$_.Type -eq 'Playback'} | Format-Table -AutoSize")
    elif kind == "input":
        out = _ps("Get-AudioDevice -List | Where-Object {$_.Type -eq 'Recording'} | Format-Table -AutoSize")
    else:
        out = _ps("Get-AudioDevice -List | Format-Table -AutoSize")
    return out if out else "No audio devices found (install GetAudioDevice module)"


def _set_output_device(params: dict) -> str:
    name = params.get("name", "")
    index = params.get("index")
    if index:
        _ps(f"Set-AudioDevice -PlaybackDeviceId {index}")
        return f"Set output device to index {index}"
    if name:
        _ps(f"Set-AudioDevice -PlaybackFriendlyName '{name}'")
        return f"Set output to {name}"
    return "Provide device name or index"


def _set_input_device(params: dict) -> str:
    name = params.get("name", "")
    index = params.get("index")
    if index:
        _ps(f"Set-AudioDevice -RecordingDeviceId {index}")
        return f"Set input device to index {index}"
    if name:
        _ps(f"Set-AudioDevice -RecordingFriendlyName '{name}'")
        return f"Set input to {name}"
    return "Provide device name or index"


def _set_volume(params: dict) -> str:
    level = params.get("level", 50)
    import pyautogui
    # Use nircmd or PowerShell to set volume
    _ps(f"$wsh = New-Object -ComObject WScript.Shell; 1..50 | ForEach-Object {{$wsh.SendKeys([char]174)}}; 1..{int(level)//2} | ForEach-Object {{$wsh.SendKeys([char]175)}}")
    return f"Volume set to ~{level}%"


def _get_volume(params: dict) -> str:
    out = _ps("(Get-AudioDevice -PlaybackVolume)")
    return f"Volume: {out}%" if out else "Volume info unavailable"


def _mute(params: dict) -> str:
    _ps("Set-AudioDevice -PlaybackMute $true")
    return "Muted"


def _unmute(params: dict) -> str:
    _ps("Set-AudioDevice -PlaybackMute $false")
    return "Unmuted"


def _test_speakers(params: dict) -> str:
    _ps("[System.Media.SystemSounds]::Hand.Play()")
    return "Playing test sound"
