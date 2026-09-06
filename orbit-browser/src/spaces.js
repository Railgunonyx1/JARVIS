/**
 * JARVIS Orbit — Spaces Module
 *
 * Implements browsing environments inspired by Arc Browser's Spaces.
 *
 * Features:
 * - Separate browsing contexts (Work, Personal, Research, etc.)
 * - Per-space cookies and storage
 * - Space-specific profiles
 * - Quick switching between spaces
 */

// ── Default Spaces ────────────────────────────────────────────────
const DEFAULT_SPACES = [
  {
    id: "work",
    name: "Work",
    icon: "💼",
    color: "#8AA4C8",
    description: "Professional browsing",
    isActive: true,
  },
  {
    id: "personal",
    name: "Personal",
    icon: "🏠",
    color: "#6F9B6A",
    description: "Personal browsing",
    isActive: false,
  },
  {
    id: "research",
    name: "Research",
    icon: "🔬",
    color: "#C9A227",
    description: "Research and learning",
    isActive: false,
  },
  {
    id: "dev",
    name: "Development",
    icon: "💻",
    color: "#D71921",
    description: "Development and coding",
    isActive: false,
  },
];

// ── Space Class ───────────────────────────────────────────────────
class Space {
  constructor(config) {
    this.id = config.id;
    this.name = config.name;
    this.icon = config.icon;
    this.color = config.color;
    this.description = config.description;
    this.isActive = config.isActive || false;
    this.tabs = [];
    this.cookies = {};
    this.storage = {};
    this.history = [];
    this.bookmarks = [];
  }

  addTab(tab) {
    this.tabs.push(tab);
  }

  removeTab(tabId) {
    this.tabs = this.tabs.filter(t => t.id !== tabId);
  }

  getTab(tabId) {
    return this.tabs.find(t => t.id === tabId);
  }

  clearTabs() {
    this.tabs = [];
  }
}

// ── Spaces Module ─────────────────────────────────────────────────
class SpacesModule {
  constructor() {
    this.spaces = new Map();
    this.activeSpaceId = null;
    this.init();
  }

  /**
   * Initialize with default spaces
   */
  init() {
    DEFAULT_SPACES.forEach(space => {
      this.spaces.set(space.id, new Space(space));
      if (space.isActive) {
        this.activeSpaceId = space.id;
      }
    });
  }

  /**
   * Get all spaces
   */
  getAll() {
    return Array.from(this.spaces.values());
  }

  /**
   * Get active space
   */
  getActive() {
    return this.spaces.get(this.activeSpaceId);
  }

  /**
   * Switch to a space
   */
  switchTo(spaceId) {
    const space = this.spaces.get(spaceId);
    if (!space) return false;

    // Deactivate current
    if (this.activeSpaceId) {
      const current = this.spaces.get(this.activeSpaceId);
      if (current) current.isActive = false;
    }

    // Activate new
    space.isActive = true;
    this.activeSpaceId = spaceId;

    return space;
  }

  /**
   * Create a new space
   */
  create(config) {
    const id = config.id || `space-${Date.now()}`;
    const space = new Space({
      id,
      name: config.name || "New Space",
      icon: config.icon || "📁",
      color: config.color || "#999999",
      description: config.description || "",
      isActive: false,
    });

    this.spaces.set(id, space);
    return space;
  }

  /**
   * Delete a space
   */
  delete(spaceId) {
    if (spaceId === this.activeSpaceId) return false;
    return this.spaces.delete(spaceId);
  }

  /**
   * Rename a space
   */
  rename(spaceId, newName) {
    const space = this.spaces.get(spaceId);
    if (space) {
      space.name = newName;
      return true;
    }
    return false;
  }

  /**
   * Update space color
   */
  updateColor(spaceId, color) {
    const space = this.spaces.get(spaceId);
    if (space) {
      space.color = color;
      return true;
    }
    return false;
  }

  /**
   * Get space for a tab
   */
  getSpaceForTab(tabId) {
    for (const space of this.spaces.values()) {
      if (space.getTab(tabId)) {
        return space;
      }
    }
    return null;
  }

  /**
   * Move tab to space
   */
  moveTabToSpace(tabId, targetSpaceId) {
    // Find current space
    const currentSpace = this.getSpaceForTab(tabId);
    const targetSpace = this.spaces.get(targetSpaceId);

    if (!targetSpace) return false;

    // Remove from current
    if (currentSpace) {
      currentSpace.removeTab(tabId);
    }

    // Add to target (tab object would need to be passed)
    // This is a simplified version
    return true;
  }

  /**
   * Export spaces data
   */
  export() {
    const data = {};
    for (const [id, space] of this.spaces) {
      data[id] = {
        name: space.name,
        icon: space.icon,
        color: space.color,
        description: space.description,
        tabCount: space.tabs.length,
      };
    }
    return data;
  }

  /**
   * Import spaces data
   */
  import(data) {
    for (const [id, config] of Object.entries(data)) {
      if (!this.spaces.has(id)) {
        this.create({ id, ...config });
      }
    }
  }

  /**
   * Get status
   */
  getStatus() {
    return {
      totalSpaces: this.spaces.size,
      activeSpace: this.activeSpaceId,
      spaces: this.getAll().map(s => ({
        id: s.id,
        name: s.name,
        icon: s.icon,
        tabCount: s.tabs.length,
        isActive: s.isActive,
      })),
    };
  }
}

// ── Export ─────────────────────────────────────────────────────────
module.exports = { SpacesModule, DEFAULT_SPACES };
