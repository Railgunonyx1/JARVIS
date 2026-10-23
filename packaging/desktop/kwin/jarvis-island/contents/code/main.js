// Keeps the JARVIS Dynamic Island pinned to the top-centre of its output.
// Wayland does not let clients position their own toplevels, so KWin does it.

var APP_ID = "jarvis-island";
var TOP_MARGIN = 8;
var AREA_PLACEMENT = 0;

function isIsland(w) {
    if (!w) {
        return false;
    }
    return w.resourceClass === APP_ID ||
           w.resourceName === APP_ID ||
           w.desktopFileName === APP_ID;
}

function islandArea(w) {
    if (typeof workspace.clientArea === "function") {
        var a = workspace.clientArea(AREA_PLACEMENT, w);
        if (a && a.width > 0 && a.height > 0) {
            return a;
        }
    }
    var s = workspace.activeOutput || workspace.activeScreen;
    return s && s.workArea ? s.workArea : null;
}

function centre(w) {
    if (!isIsland(w) || w.deleted) {
        return;
    }
    var a = islandArea(w);
    if (!a) {
        return;
    }
    var g = w.frameGeometry;
    if (!g || g.width <= 0) {
        return;
    }
    var x = a.x + Math.round((a.width - g.width) / 2);
    var y = a.y + TOP_MARGIN;
    if (Math.abs(g.x - x) <= 1 && Math.abs(g.y - y) <= 1) {
        return;
    }
    try {
        w.frameGeometry = Qt.rect(x, y, g.width, g.height);
    } catch (e) {
        console.warn("jarvis-island: cannot set frameGeometry:", e);
    }
}

function attach(w) {
    if (!isIsland(w)) {
        return;
    }
    w.keepAbove = true;
    w.skipTaskbar = true;
    try {
        w.skipSwitcher = true;
    } catch (e) {
    }
    centre(w);
    // Re-centre whenever the pill morphs (expand/collapse changes only width)
    // or moves to another output. The guard in centre() stops the feedback loop.
    try {
        w.frameGeometryChanged.connect(function () { centre(w); });
    } catch (e) {
    }
    try {
        w.outputChanged.connect(function () { centre(w); });
    } catch (e) {
    }
}

workspace.windowAdded.connect(attach);

var existing = workspace.windowList ? workspace.windowList() : workspace.clientList();
for (var i = 0; i < existing.length; i++) {
    attach(existing[i]);
}
