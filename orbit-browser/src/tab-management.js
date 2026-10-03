/**
 * JARVIS Orbit — Tab Management Module
 * 
 * Advanced tab features inspired by:
 * - Chrome Tab Groups (color-coded, collapsible)
 * - Arc Browser (spaces, favorites)
 * - Edge Vertical Tabs
 * - Vivaldi Tab Stacks
 * 
 * Features:
 * - Tab grouping with colors
 * - Tab pinning
 * - Tab preview on hover
 * - Tab search
 * - Recently closed tabs
 * - Tab dragging/reordering
 */

class TabManagement {
  constructor() {
    this.groups = new Map();
    this.pinnedTabs = new Set();
    this.tabHistory = [];
    this.maxHistory = 50;
    this.previewTimeout = null;
    this.previewElement = null;
    
    this.colors = [
      { id: 'grey', name: 'Grey', value: '#5f6368' },
      { id: 'blue', name: 'Blue', value: '#4285f4' },
      { id: 'red', name: 'Red', value: '#ea4335' },
      { id: 'yellow', name: 'Yellow', value: '#fbbc05' },
      { id: 'green', name: 'Green', value: '#34a853' },
      { id: 'pink', name: 'Pink', value: '#ff6d9f' },
      { id: 'purple', name: 'Purple', value: '#a142f4' },
      { id: 'cyan', name: 'Cyan', value: '#24c1e0' },
      { id: 'orange', name: 'Orange', value: '#fa903e' },
    ];
    
    this.init();
  }

  init() {
    this.setupEventListeners();
    this.loadPersistedState();
    this.createPreviewElement();
  }

  setupEventListeners() {
    // Tab hover for preview
    document.addEventListener('mouseover', (e) => {
      const tabEl = e.target.closest('.tab');
      if (tabEl) {
        this.startPreviewTimer(tabEl);
      }
    });

    document.addEventListener('mouseout', (e) => {
      const tabEl = e.target.closest('.tab');
      if (tabEl) {
        this.clearPreviewTimer();
      }
    });

    // Keyboard shortcuts
    document.addEventListener('keydown', (e) => {
      // Ctrl+Shift+G: Group selected tabs
      if (e.ctrlKey && e.shiftKey && e.key.toLowerCase() === 'g') {
        e.preventDefault();
        this.groupSelectedTabs();
      }
      
      // Ctrl+Shift+P: Pin/unpin tab
      if (e.ctrlKey && e.shiftKey && e.key.toLowerCase() === 'p') {
        e.preventDefault();
        this.togglePinTab();
      }
      
      // Ctrl+Shift+H: Show recently closed
      if (e.ctrlKey && e.shiftKey && e.key.toLowerCase() === 'h') {
        e.preventDefault();
        this.showRecentlyClosed();
      }
      
      // Ctrl+F: Tab search (when focus is not in input)
      if (e.ctrlKey && e.key.toLowerCase() === 'f' && !this.isInputFocused()) {
        e.preventDefault();
        this.showTabSearch();
      }
    });
  }

  loadPersistedState() {
    try {
      const saved = localStorage.getItem('tab-management');
      if (saved) {
        const state = JSON.parse(saved);
        this.groups = new Map(state.groups || []);
        this.pinnedTabs = new Set(state.pinnedTabs || []);
        this.tabHistory = state.tabHistory || [];
      }
    } catch (e) {
      console.warn('[TABS] Failed to load state:', e);
    }
  }

  persistState() {
    try {
      localStorage.setItem('tab-management', JSON.stringify({
        groups: Array.from(this.groups.entries()),
        pinnedTabs: Array.from(this.pinnedTabs),
        tabHistory: this.tabHistory,
      }));
    } catch (e) {
      console.warn('[TABS] Failed to persist state:', e);
    }
  }

  // ── Tab Groups ──────────────────────────────────────────────────
  
  createGroup(name, color = 'grey') {
    const id = `group-${Date.now()}`;
    const group = {
      id,
      name,
      color,
      collapsed: false,
      tabs: [],
      created: Date.now(),
    };
    
    this.groups.set(id, group);
    this.persistState();
    this.notify('group-created', { group });
    
    return group;
  }

  deleteGroup(id) {
    if (!this.groups.has(id)) return false;
    
    // Uncollapse all tabs in the group
    const group = this.groups.get(id);
    group.tabs.forEach(tabId => {
      this.ungroupTab(tabId);
    });
    
    this.groups.delete(id);
    this.persistState();
    this.notify('group-deleted', { groupId: id });
    
    return true;
  }

  renameGroup(id, name) {
    const group = this.groups.get(id);
    if (!group) return false;
    
    group.name = name;
    this.groups.set(id, group);
    this.persistState();
    
    return true;
  }

  changeGroupColor(id, color) {
    const group = this.groups.get(id);
    if (!group) return false;
    
    group.color = color;
    this.groups.set(id, group);
    this.persistState();
    
    return true;
  }

  toggleGroupCollapse(id) {
    const group = this.groups.get(id);
    if (!group) return false;
    
    group.collapsed = !group.collapsed;
    this.groups.set(id, group);
    this.persistState();
    
    this.notify('group-toggled', { group });
    
    return group.collapsed;
  }

  addTabToGroup(tabId, groupId) {
    const group = this.groups.get(groupId);
    if (!group) return false;
    
    // Remove from any existing group
    this.ungroupTab(tabId);
    
    // Add to new group
    group.tabs.push(tabId);
    this.groups.set(groupId, group);
    this.persistState();
    
    this.notify('tab-grouped', { tabId, groupId });
    
    return true;
  }

  ungroupTab(tabId) {
    for (const [groupId, group] of this.groups) {
      const index = group.tabs.indexOf(tabId);
      if (index !== -1) {
        group.tabs.splice(index, 1);
        this.groups.set(groupId, group);
        
        // Delete group if empty
        if (group.tabs.length === 0) {
          this.groups.delete(groupId);
        }
        
        this.persistState();
        this.notify('tab-ungrouped', { tabId, groupId });
        
        return true;
      }
    }
    return false;
  }

  getGroupForTab(tabId) {
    for (const [groupId, group] of this.groups) {
      if (group.tabs.includes(tabId)) {
        return group;
      }
    }
    return null;
  }

  groupSelectedTabs() {
    // Get selected tabs (implementation depends on UI)
    const selectedTabs = this.getSelectedTabs();
    if (selectedTabs.length < 2) return null;
    
    const group = this.createGroup('New Group');
    selectedTabs.forEach(tabId => {
      this.addTabToGroup(tabId, group.id);
    });
    
    return group;
  }

  // ── Tab Pinning ─────────────────────────────────────────────────
  
  pinTab(tabId) {
    this.pinnedTabs.add(tabId);
    this.persistState();
    this.notify('tab-pinned', { tabId });
  }

  unpinTab(tabId) {
    this.pinnedTabs.delete(tabId);
    this.persistState();
    this.notify('tab-unpinned', { tabId });
  }

  togglePinTab() {
    const activeTabId = this.getActiveTabId();
    if (!activeTabId) return;
    
    if (this.pinnedTabs.has(activeTabId)) {
      this.unpinTab(activeTabId);
    } else {
      this.pinTab(activeTabId);
    }
  }

  isPinned(tabId) {
    return this.pinnedTabs.has(tabId);
  }

  // ── Tab Preview ─────────────────────────────────────────────────
  
  createPreviewElement() {
    this.previewElement = document.createElement('div');
    this.previewElement.className = 'tab-preview';
    this.previewElement.style.display = 'none';
    document.body.appendChild(this.previewElement);
  }

  startPreviewTimer(tabEl) {
    this.clearPreviewTimer();
    
    this.previewTimeout = setTimeout(() => {
      this.showPreview(tabEl);
    }, 500); // Show after 500ms hover
  }

  clearPreviewTimer() {
    if (this.previewTimeout) {
      clearTimeout(this.previewTimeout);
      this.previewTimeout = null;
    }
    this.hidePreview();
  }

  showPreview(tabEl) {
    const tabId = tabEl.dataset.id;
    if (!tabId) return;
    
    // Get tab info
    const tabInfo = this.getTabInfo(tabId);
    if (!tabInfo) return;
    
    // Position preview near the tab
    const rect = tabEl.getBoundingClientRect();
    
    this.previewElement.innerHTML = `
      <div class="tab-preview-title">${this.escapeHtml(tabInfo.title || 'New Tab')}</div>
      <div class="tab-preview-url">${this.escapeHtml(tabInfo.url || '')}</div>
      <div class="tab-preview-favicon">
        ${tabInfo.favicon ? `<img src="${tabInfo.favicon}" alt="">` : ''}
      </div>
    `;
    
    this.previewElement.style.display = 'block';
    this.previewElement.style.left = `${rect.left}px`;
    this.previewElement.style.top = `${rect.bottom + 4}px`;
  }

  hidePreview() {
    if (this.previewElement) {
      this.previewElement.style.display = 'none';
    }
  }

  // ── Tab Search ──────────────────────────────────────────────────
  
  showTabSearch() {
    // Create search overlay
    const overlay = document.createElement('div');
    overlay.className = 'tab-search-overlay';
    overlay.innerHTML = `
      <div class="tab-search-container">
        <input type="text" class="tab-search-input" placeholder="Search tabs..." autofocus />
        <div class="tab-search-results"></div>
      </div>
    `;
    
    document.body.appendChild(overlay);
    
    const input = overlay.querySelector('.tab-search-input');
    const results = overlay.querySelector('.tab-search-results');
    
    // Focus input
    input.focus();
    
    // Handle input
    input.addEventListener('input', () => {
      const query = input.value.toLowerCase();
      const tabs = this.searchTabs(query);
      this.renderSearchResults(results, tabs);
    });
    
    // Handle keyboard
    input.addEventListener('keydown', (e) => {
      if (e.key === 'Escape') {
        overlay.remove();
      } else if (e.key === 'Enter') {
        const firstResult = results.querySelector('.tab-search-item');
        if (firstResult) {
          const tabId = firstResult.dataset.tabId;
          this.activateTab(tabId);
          overlay.remove();
        }
      }
    });
    
    // Close on click outside
    overlay.addEventListener('click', (e) => {
      if (e.target === overlay) {
        overlay.remove();
      }
    });
  }

  searchTabs(query) {
    const tabs = this.getAllTabs();
    return tabs.filter(tab => 
      (tab.title || '').toLowerCase().includes(query) ||
      (tab.url || '').toLowerCase().includes(query)
    );
  }

  renderSearchResults(container, tabs) {
    container.innerHTML = tabs.map(tab => `
      <div class="tab-search-item" data-tab-id="${tab.id}">
        <div class="tab-search-title">${this.escapeHtml(tab.title || 'New Tab')}</div>
        <div class="tab-search-url">${this.escapeHtml(tab.url || '')}</div>
      </div>
    `).join('');
    
    // Add click handlers
    container.querySelectorAll('.tab-search-item').forEach(item => {
      item.addEventListener('click', () => {
        this.activateTab(item.dataset.tabId);
        item.closest('.tab-search-overlay').remove();
      });
    });
  }

  // ── Recently Closed ─────────────────────────────────────────────
  
  addToHistory(tab) {
    this.tabHistory.unshift({
      id: tab.id,
      url: tab.url,
      title: tab.title,
      closedAt: Date.now(),
    });
    
    // Keep only recent tabs
    if (this.tabHistory.length > this.maxHistory) {
      this.tabHistory.pop();
    }
    
    this.persistState();
  }

  showRecentlyClosed() {
    // Create overlay
    const overlay = document.createElement('div');
    overlay.className = 'recently-closed-overlay';
    overlay.innerHTML = `
      <div class="recently-closed-container">
        <h3>Recently Closed</h3>
        <div class="recently-closed-list">
          ${this.tabHistory.length === 0 ? 
            '<div class="recently-closed-empty">No recently closed tabs</div>' :
            this.tabHistory.map(tab => `
              <div class="recently-closed-item" data-url="${this.escapeHtml(tab.url)}">
                <div class="recently-closed-title">${this.escapeHtml(tab.title || 'New Tab')}</div>
                <div class="recently-closed-url">${this.escapeHtml(tab.url || '')}</div>
                <div class="recently-closed-time">${this.formatTime(tab.closedAt)}</div>
              </div>
            `).join('')
          }
        </div>
      </div>
    `;
    
    document.body.appendChild(overlay);
    
    // Add click handlers
    overlay.querySelectorAll('.recently-closed-item').forEach(item => {
      item.addEventListener('click', () => {
        this.openUrl(item.dataset.url);
        overlay.remove();
      });
    });
    
    // Close on click outside
    overlay.addEventListener('click', (e) => {
      if (e.target === overlay) {
        overlay.remove();
      }
    });
    
    // Close on Escape
    overlay.addEventListener('keydown', (e) => {
      if (e.key === 'Escape') {
        overlay.remove();
      }
    });
  }

  // ── Helper Methods ──────────────────────────────────────────────
  
  getAllTabs() {
    // This would interface with the main tab system
    return Array.from(document.querySelectorAll('.tab')).map(el => ({
      id: el.dataset.id,
      title: el.querySelector('.tab-title')?.textContent || '',
      url: el.dataset.url || '',
      favicon: el.querySelector('.tab-fav img')?.src || '',
    }));
  }

  getActiveTabId() {
    const activeTab = document.querySelector('.tab.active');
    return activeTab?.dataset.id;
  }

  getSelectedTabs() {
    return Array.from(document.querySelectorAll('.tab.selected')).map(el => el.dataset.id);
  }

  getTabInfo(tabId) {
    const tabEl = document.querySelector(`.tab[data-id="${tabId}"]`);
    if (!tabEl) return null;
    
    return {
      id: tabId,
      title: tabEl.querySelector('.tab-title')?.textContent || '',
      url: tabEl.dataset.url || '',
      favicon: tabEl.querySelector('.tab-fav img')?.src || '',
    };
  }

  activateTab(tabId) {
    // Interface with main tab system
    if (window.activateTab) {
      window.activateTab(tabId);
    }
  }

  openUrl(url) {
    if (window.navigateTo) {
      window.navigateTo(url);
    }
  }

  formatTime(timestamp) {
    const diff = Date.now() - timestamp;
    const minutes = Math.floor(diff / 60000);
    const hours = Math.floor(diff / 3600000);
    const days = Math.floor(diff / 86400000);
    
    if (minutes < 1) return 'Just now';
    if (minutes < 60) return `${minutes}m ago`;
    if (hours < 24) return `${hours}h ago`;
    return `${days}d ago`;
  }

  escapeHtml(str) {
    const div = document.createElement('div');
    div.textContent = str;
    return div.innerHTML;
  }

  isInputFocused() {
    const active = document.activeElement;
    return active && (active.tagName === 'INPUT' || active.tagName === 'TEXTAREA');
  }

  notify(type, data) {
    const event = new CustomEvent('tab-management-event', {
      detail: { type, data }
    });
    window.dispatchEvent(event);
  }
}

// Export
window.TabManagement = TabManagement;
window.tabManagement = new TabManagement();
