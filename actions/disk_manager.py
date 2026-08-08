"""Disk Manager — disk info, cleanup, temp files for JARVIS MK-X."""

import os
import shutil
import subprocess
import logging
from pathlib import Path

logger = logging.getLogger("jarvis.actions.disk_manager")


def disk_action(action: str, parameters: dict, **kwargs) -> str:
    handlers = {
        "info": _disk_info,
        "cleanup": _disk_cleanup,
        "temp_clean": _clean_temp,
        "recycle": _empty_recycle,
        "disk_usage": _disk_usage,
        "defrag_check": _defrag_check,
        "disk_health": _disk_health,
    }
    handler = handlers.get(action)
    if not handler:
        return f"Unknown disk action: {action}"
    try:
        return handler(parameters)
    except Exception as e:
        logger.error("Disk action '%s' failed: %s", action, e)
        return f"Disk operation failed: {e}"


def _ps(cmd: str) -> str:
    try:
        r = subprocess.run(
            ["powershell", "-NoProfile", "-Command", cmd],
            capture_output=True, text=True, timeout=30,
        )
        return r.stdout.strip()
    except Exception as e:
        return f"Error: {e}"


def _disk_info(params: dict) -> str:
    out = _ps("Get-PSDrive -PSProvider FileSystem | Select-Object Name, @{N='Used(GB)';E={[math]::Round($_.Used/1GB,2)}}, @{N='Free(GB)';E={[math]::Round($_.Free/1GB,2)}}, @{N='Total(GB)';E={[math]::Round(($_.Used+$_.Free)/1GB,2)}} | Format-Table -AutoSize")
    return out if out else "Disk info unavailable"


def _disk_cleanup(params: dict) -> str:
    freed = 0
    locations = [
        Path.home() / "AppData" / "Local" / "Temp",
        Path("C:/Windows/Temp"),
        Path.home() / "AppData" / "Local" / "Microsoft" / "Windows" / "INetCache",
        Path.home() / "AppData" / "Local" / "Microsoft" / "Windows" / "Temporary Internet Files",
    ]
    for loc in locations:
        if loc.exists():
            for item in loc.iterdir():
                try:
                    if item.is_file():
                        size = item.stat().st_size
                        item.unlink()
                        freed += size
                    elif item.is_dir():
                        size = sum(f.stat().st_size for f in item.rglob("*") if f.is_file())
                        shutil.rmtree(item)
                        freed += size
                except Exception:
                    pass

    freed_mb = freed / (1024 * 1024)
    return f"Freed {freed_mb:.1f} MB of disk space"


def _clean_temp(params: dict) -> str:
    temp = Path.home() / "AppData" / "Local" / "Temp"
    count = 0
    freed = 0
    if temp.exists():
        for item in temp.iterdir():
            try:
                if item.is_file():
                    freed += item.stat().st_size
                    item.unlink()
                    count += 1
                elif item.is_dir():
                    freed += sum(f.stat().st_size for f in item.rglob("*") if f.is_file())
                    shutil.rmtree(item)
                    count += 1
            except Exception:
                pass
    return f"Cleaned {count} temp items, freed {freed / (1024*1024):.1f} MB"


def _empty_recycle(params: dict) -> str:
    _ps("(New-Object -ComObject Shell.Application).NameSpace(10).Items() | ForEach-Object { Remove-Item $_.Path -Force -Recurse }")
    return "Recycle bin emptied"


def _disk_usage(params: dict) -> str:
    path = params.get("path", "C:\\")
    ps_cmd = (
        "Get-ChildItem -Path '" + path + "' -Recurse -ErrorAction SilentlyContinue "
        "| Measure-Object -Property Length -Sum "
        "| Select-Object @{N='Size(GB)';E={[math]::Round($_.Sum/1GB,2)}}, Count "
        "| Format-Table -AutoSize"
    )
    out = _ps(ps_cmd)
    return out if out else "Usage info unavailable"


def _defrag_check(params: dict) -> str:
    out = _ps("Optimize-Volume -DriveLetter C -Analyze | Select-Object FragmentationPercentage")
    return f"Fragmentation analysis:\n{out}" if out else "Defrag check unavailable"


def _disk_health(params: dict) -> str:
    out = _ps("Get-PhysicalDisk | Select-Object FriendlyName, MediaType, HealthStatus, Size | Format-Table -AutoSize")
    return out if out else "Disk health info unavailable"
