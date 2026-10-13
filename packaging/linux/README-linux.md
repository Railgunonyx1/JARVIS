# JARVIS Orbit — Linux packaging

## What was added

- `packaging/linux/launch-orbit.sh` — single-command launcher. Bring up
  kernel (8170), bridge (8171) and the Orbit browser window in one shot,
  then print a short status line.
- `packaging/linux/jarvis-orbit.desktop` — desktop entry that points at
  `launch-orbit.sh` (no terminal, no waiting).
- `packaging/linux/install-icons.sh` — installs the packaged icons into
  `~/.local/share/icons/hicolor` so `Icon=jarvis-orbit` resolves.
- `packaging/linux/local-install.sh` — one-shot install: icons + desktop
  entry + chmod on the launcher. Run it once after cloning.

## Install (user-local, no root)

```bash
cd packaging/linux
bash local-install.sh
```

That puts:

- icons into `~/.local/share/icons/hicolor/.../apps/jarvis-orbit.png`
- a desktop entry into `~/.local/share/applications/jarvis-orbit.desktop`
- `launch-orbit.sh` and `jarvis-orbit.sh` as executable

After that, "JARVIS Orbit" shows up in the app grid/launcher.

## Launch

- From the app grid: **JARVIS Orbit**
- From a terminal:

```bash
bash packaging/linux/launch-orbit.sh
```

Both do the same thing: start JARVIS services if they're not already up,
then launch (or focus) the Orbit browser.

## Electron binary

The workspace is an Electron app (`orbit-browser/`, pinned electron
44.5.1). `JARVIS.sh` picks the runtime from, in order:

1. `orbit-browser/node_modules/electron/dist/electron` (preferred, what
   `launch-orbit.sh` now uses directly)
2. `orbit-browser/node_modules/.bin/electron`
3. a globally-installed `electron`
4. `node orbit-browser/node_modules/electron/cli.js` (repository binary)

If none of those exist, `JARVIS.sh` runs `npm ci` in `orbit-browser/`
to produce them. On this machine the binary is already present at
`orbit-browser/node_modules/electron/dist/electron`.

## Current status on this machine

- Electron binary: present and executable.
- Kernel (8170) + bridge (8171): start up via `JARVIS.sh`.
- Orbit browser window: launches from `launch-orbit.sh` / desktop entry.

The Orbit window currently exercises the JARVIS agent stack end-to-end
(kernel + bridge + browser), and the Electron process talks to the
bridge over the local WebSocket.
