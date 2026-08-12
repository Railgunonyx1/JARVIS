"""App launcher — cross-platform app opening with alias resolution."""

import logging
import platform
import shutil
import subprocess
import time

logger = logging.getLogger("jarvis.actions.open_app")
_OS = platform.system()

# App aliases: {alias: {OS: command}}
_ALIASES = {}
def _a(name, win, mac, linux):
    _ALIASES[name] = {"Windows": win, "Darwin": mac, "Linux": linux}

# Browsers
for n, w, m in [("chrome","chrome","Google Chrome"),("firefox","firefox","Firefox"),("edge","msedge","Microsoft Edge"),("brave","brave","Brave Browser"),("opera","opera","Opera")]:
    _a(n, w, m, w.replace("msedge","microsoft-edge").replace("Google Chrome","google-chrome"))
_a("safari", "msedge", "Safari", "firefox")

# Communication
for n, w, m in [("whatsapp","WhatsApp","WhatsApp"),("telegram","Telegram","Telegram"),("discord","Discord","Discord"),("slack","Slack","Slack"),("zoom","Zoom","zoom.us"),("teams","msteams","Microsoft Teams"),("skype","skype","Skype"),("signal","signal","Signal")]:
    _a(n, w, m, w.lower())

# Media
for n, w, m in [("spotify","Spotify","Spotify"),("vlc","vlc","VLC"),("netflix","Netflix","Netflix")]:
    _a(n, w, m, w.lower() if w.lower() != "netflix" else "firefox")

# Dev
for n, w, m in [("vscode","code","Visual Studio Code"),("visual studio code","code","Visual Studio Code"),("code","code","Visual Studio Code"),("postman","Postman","Postman"),("figma","Figma","Figma"),("blender","blender","Blender"),("git","git-bash","Terminal")]:
    _a(n, w, m, w.replace("git-bash","bash"))
_a("terminal", "wt", "Terminal", "x-terminal-emulator")
_a("cmd", "cmd.exe", "Terminal", "bash")
_a("powershell", "powershell.exe", "Terminal", "bash")

# Productivity
for n, w, m in [("word","winword","Microsoft Word"),("excel","excel","Microsoft Excel"),("powerpoint","powerpnt","Microsoft PowerPoint"),("libreoffice","soffice","LibreOffice")]:
    _a(n, w, m, f"libreoffice --{'writer' if n=='word' else 'calc' if n=='excel' else 'impress'}")

# Utilities
for n, w, m in [("notepad","notepad.exe","TextEdit"),("textedit","notepad.exe","TextEdit"),("explorer","explorer.exe","Finder"),("file explorer","explorer.exe","Finder"),("finder","explorer.exe","Finder"),("task manager","taskmgr.exe","Activity Monitor"),("settings","ms-settings:","System Preferences"),("calculator","calc.exe","Calculator"),("paint","mspaint.exe","Preview")]:
    _a(n, w, m, {"notepad":"gedit","textedit":"gedit","explorer":"nautilus","file explorer":"nautilus","finder":"nautilus","task manager":"gnome-system-monitor","settings":"gnome-control-center","calculator":"gnome-calculator","paint":"gimp"}.get(n, w.lower()))

# Social/Other
for n, w, m in [("instagram","Instagram","Instagram"),("tiktok","TikTok","TikTok"),("notion","Notion","Notion"),("obsidian","Obsidian","Obsidian"),("capcut","CapCut","CapCut"),("steam","steam","Steam"),("epic","EpicGamesLauncher","Epic Games Launcher"),("epic games","EpicGamesLauncher","Epic Games Launcher")]:
    _a(n, w, m, w.lower() if m not in ("Instagram","TikTok") else "firefox")


def _normalize(raw: str) -> str:
    key = raw.lower().strip()
    if key in _ALIASES:
        return _ALIASES[key].get(_OS, raw)
    for alias, os_map in _ALIASES.items():
        if alias == key or key == alias:
            return os_map.get(_OS, raw)
    return raw


def _launch_windows(app: str) -> bool:
    if shutil.which(app) or shutil.which(app.split(".")[0]):
        try:
            subprocess.Popen(app, shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            time.sleep(0.3)
            return True
        except Exception:
            pass
    if ":" in app:
        try:
            subprocess.Popen(f"start {app}", shell=True)
            time.sleep(0.3)
            return True
        except Exception:
            pass
    try:
        import pyautogui
        pyautogui.press("win")
        time.sleep(0.5)
        pyautogui.write(app, interval=0.05)
        time.sleep(0.5)
        pyautogui.press("enter")
        time.sleep(0.3)
        return True
    except Exception:
        return False


def _launch_macos(app: str) -> bool:
    for name in [app, f"{app}.app"]:
        try:
            if subprocess.run(["open", "-a", name], capture_output=True, timeout=8).returncode == 0:
                time.sleep(1.0)
                return True
        except Exception:
            pass
    binary = shutil.which(app) or shutil.which(app.lower())
    if binary:
        try:
            subprocess.Popen([binary], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            time.sleep(1.0)
            return True
        except Exception:
            pass
    try:
        import pyautogui
        pyautogui.hotkey("command", "space")
        time.sleep(0.6)
        pyautogui.write(app, interval=0.05)
        time.sleep(0.8)
        pyautogui.press("enter")
        time.sleep(1.5)
        return True
    except Exception:
        return False


_TERMINAL_FALLBACKS = ["x-terminal-emulator", "gnome-terminal", "konsole", "xfce4-terminal", "xterm", "alacritty", "kitty"]

def _launch_linux(app: str) -> bool:
    if "terminal" in app.lower() or app == "x-terminal-emulator":
        for t in _TERMINAL_FALLBACKS:
            if shutil.which(t):
                try:
                    subprocess.Popen([t], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    time.sleep(1.0)
                    return True
                except Exception:
                    continue
    binary = (shutil.which(app) or shutil.which(app.lower()) or
              shutil.which(app.lower().replace(" ", "-")) or shutil.which(app.lower().replace(" ", "_")))
    if binary:
        try:
            subprocess.Popen([binary], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            time.sleep(1.0)
            return True
        except Exception:
            pass
    try:
        subprocess.run(["xdg-open", app], capture_output=True, timeout=5)
        return True
    except Exception:
        return False


_LAUNCHERS = {"Windows": _launch_windows, "Darwin": _launch_macos, "Linux": _launch_linux}


def open_app(parameters=None, **kwargs) -> str:
    app_name = (parameters or {}).get("app_name", "").strip()
    if not app_name:
        return "No application name provided."
    launcher = _LAUNCHERS.get(_OS)
    if not launcher:
        return f"Unsupported OS: {_OS}"
    normalized = _normalize(app_name)
    try:
        if launcher(normalized):
            return f"Opened {app_name}."
        if normalized.lower() != app_name.lower() and launcher(app_name):
            return f"Opened {app_name}."
        return f"Could not confirm {app_name} launched. It may not be installed."
    except Exception as e:
        return f"Failed to open {app_name}: {e}"
