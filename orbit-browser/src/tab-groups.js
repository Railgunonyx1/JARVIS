/**
 * JARVIS Orbit — Tab Groups
 * Chrome/Edge-style collapsible tab groups with color coding
 */
class TabGroups {
  constructor() {
    this.groups = new Map();
    this.tabGroupMap = new Map();
    this.colors = ['#4285f4', '#ea4335', '#fbbc05', '#34a853', '#ff6d01', '#46bdc6', '#7b1fa2', '#c2185b'];
    this.nextColorIndex = 0;
  }

  createGroup(name, color) {
    const id = 'group-' + Date.now();
    const group = {
      id,
      name: name || 'New Group',
      color: color || this.colors[this.nextColorIndex % this.colors.length],
      collapsed: false,
      tabs: []
    };
    this.groups.set(id, group);
    this.nextColorIndex++;
    this.render();
    return group;
  }

  addTabToGroup(tabId, groupId) {
    const group = this.groups.get(groupId);
    if (!group) return;
    this.tabGroupMap.set(tabId, groupId);
    if (!group.tabs.includes(tabId)) group.tabs.push(tabId);
    this.render();
  }

  removeTabFromGroup(tabId) {
    const groupId = this.tabGroupMap.get(tabId);
    if (!groupId) return;
    const group = this.groups.get(groupId);
    if (group) group.tabs = group.tabs.filter(id => id !== tabId);
    this.tabGroupMap.delete(tabId);
    if (group && group.tabs.length === 0) this.deleteGroup(groupId);
    this.render();
  }

  deleteGroup(groupId) {
    const group = this.groups.get(groupId);
    if (group) group.tabs.forEach(tabId => this.tabGroupMap.delete(tabId));
    this.groups.delete(groupId);
    this.render();
  }

  toggleCollapse(groupId) {
    const group = this.groups.get(groupId);
    if (group) { group.collapsed = !group.collapsed; this.render(); }
  }

  renameGroup(groupId, name) {
    const group = this.groups.get(groupId);
    if (group) { group.name = name; this.render(); }
  }

  getGroupForTab(tabId) {
    return this.tabGroupMap.get(tabId) || null;
  }

  render() {
    // This would integrate with the tab strip to render groups
    // For now, it's a data model that the renderer can query
    if (window.renderTabStrip) window.renderTabStrip();
  }
}

document.addEventListener('DOMContentLoaded', () => { window.tabGroups = new TabGroups(); });
