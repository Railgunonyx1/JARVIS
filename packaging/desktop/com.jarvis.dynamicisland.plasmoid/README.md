# JARVIS Dynamic Island — Plasma 6 starter plasmoid

This is an installable KDE Plasma 6 plasmoid package. It turns the visual direction
into a native QML widget with a compact capsule, a click-to-expand control-centre
layout, and a live clock/date.

## Install on Bazzite / KDE Plasma 6

From the directory containing `com.jarvis.dynamicisland.plasmoid`:

```bash
kpackagetool6 --type Plasma/Applet --install ./com.jarvis.dynamicisland.plasmoid
```

Then:
1. Right-click the desktop or panel.
2. Choose **Enter Edit Mode** / **Add Widgets**.
3. Search for **JARVIS Dynamic Island**.
4. Drag it onto the panel. For the intended look, place it in a top panel and
   centre it using Plasma's panel alignment/spacer controls.

To update after changing QML:

```bash
kpackagetool6 --type Plasma/Applet --upgrade ./com.jarvis.dynamicisland.plasmoid
```

To remove:

```bash
kpackagetool6 --type Plasma/Applet --remove com.jarvis.dynamicisland
```

## Current scope

Implemented:
- Native Plasma 6 applet package structure.
- Compact capsule representation.
- Click-to-expand full representation.
- Live clock and date.
- Dark monochrome styling with restrained red accent.

Not yet connected:
- MPRIS media sessions.
- KDE notifications.
- Audio, brightness, Wi-Fi, Bluetooth and battery controls.
- Launcher and optional dock.
- JARVIS AI runtime.

The four expanded cards are currently visual placeholders, not working system
switches. This package is a usable UI foundation, not the completed desktop
control centre. The next engineering step is to connect each card to KDE-native
services and test it on the target Plasma 6/Bazzite version.
