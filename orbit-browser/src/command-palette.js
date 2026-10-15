/**
 * JARVIS Orbit — Command Palette
 * Vivaldi-style command palette (Ctrl+K / Cmd+K)
 * Fuzzy search across tabs, bookmarks, history, commands
 */
class CommandPalette {
  constructor() {
    this.isOpen = false;
    this.selectedIndex = 0;
    this.results = [];
    this.commands = this.getCommands();
    this.init();
  }

  init() {
    this.container = document.createElement('div');
    this.container.className = 'cmd-palette-container';
    this.container.innerHTML = `
      <div class="cmd-palette">
        <div class="cmd-search">
          <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
            <circle cx="7" cy="7" r="5" stroke="currentColor" stroke-width="1.4"/>
            <path d="M11 11l3 3" stroke="currentColor" stroke-width="1.4"/>
          </svg>
          <input type="text" id="cmdInput" placeholder="Type a command or search..." autocomplete="off" spellcheck="false" />
          <kbd class="cmd-kbd">Esc</kbd>
        </div>
        <div class="cmd-results" id="cmdResults"></div>
        <div class="cmd-footer">
          <span><kbd>↑↓</kbd> Navigate</span>
          <span><kbd>Enter</kbd> Select</span>
          <span><kbd>Esc</kbd> Close</span>
        </div>
      </div>
    `;
    document.body.appendChild(this.container);
    this.input = this.container.querySelector('#cmdInput');
    this.resultsContainer = this.container.querySelector('#cmdResults');
    this.input.addEventListener('input', () => this.onInput());
    this.input.addEventListener('keydown', (e) => this.onKeydown(e));
    this.container.addEventListener('click', (e) => { if (e.target === this.container) this.close(); });
    document.addEventListener('keydown', (e) => {
      if ((e.ctrlKey || e.metaKey) && e.key === 'k') { e.preventDefault(); this.toggle(); }
    });
  }

  getCommands() {
    return [
      { id: 'new-tab', name: 'New Tab', category: 'Navigation', icon: '➕', shortcut: 'Ctrl+T', action: () => window.electronAPI?.tabs?.create() },
      { id: 'close-tab', name: 'Close Tab', category: 'Navigation', icon: '❌', shortcut: 'Ctrl+W', action: () => window.electronAPI?.tabs?.closeActive() },
      { id: 'reload', name: 'Reload Page', category: 'Page', icon: '🔄', shortcut: 'Ctrl+R', action: () => window.electronAPI?.page?.reload() },
      { id: 'print', name: 'Print Page', category: 'Page', icon: '🖨️', shortcut: 'Ctrl+P', action: () => window.electronAPI?.page?.print() },
      { id: 'screenshot', name: 'Screenshot', category: 'Page', icon: '📷', shortcut: 'Ctrl+Shift+S', action: () => window.electronAPI?.page?.screenshot() },
      { id: 'zoom-in', name: 'Zoom In', category: 'View', icon: '🔍', shortcut: 'Ctrl++', action: () => window.electronAPI?.page?.zoomIn() },
      { id: 'zoom-out', name: 'Zoom Out', category: 'View', icon: '🔎', shortcut: 'Ctrl+-', action: () => window.electronAPI?.page?.zoomOut() },
      { id: 'zoom-reset', name: 'Reset Zoom', category: 'View', icon: '100%', shortcut: 'Ctrl+0', action: () => window.electronAPI?.page?.zoomReset() },
      { id: 'sidebar', name: 'Toggle Sidebar', category: 'View', icon: '📐', shortcut: 'Ctrl+Shift+J', action: () => window.jarvis?.toggleSidebar() },
      { id: 'devtools', name: 'Developer Tools', category: 'View', icon: '🛠️', shortcut: 'F12', action: () => window.electronAPI?.page?.toggleDevTools() },
      { id: 'jarvis-chat', name: 'Chat with JARVIS', category: 'JARVIS', icon: '🤖', action: () => window.jarvis?.focusChat() },
      { id: 'jarvis-task', name: 'Create Agent Task', category: 'JARVIS', icon: '📋', action: () => window.jarvis?.createTask() },
      { id: 'jarvis-research', name: 'Research Topic', category: 'JARVIS', icon: '🔬', action: () => window.jarvis?.research() },
      { id: 'jarvis-memory', name: 'Access Memory', category: 'JARVIS', icon: '🧠', action: () => window.jarvis?.openMemory() },
      { id: 'settings', name: 'Open Settings', category: 'Settings', icon: '⚙️', action: () => window.electronAPI?.settings?.open() },
      { id: 'history', name: 'View History', category: 'Settings', icon: '📜', shortcut: 'Ctrl+H', action: () => window.electronAPI?.history?.open() },
      { id: 'downloads', name: 'View Downloads', category: 'Settings', icon: '⬇️', shortcut: 'Ctrl+J', action: () => window.electronAPI?.downloads?.open() },
      { id: 'bookmarks', name: 'View Bookmarks', category: 'Settings', icon: '⭐', shortcut: 'Ctrl+Shift+O', action: () => window.electronAPI?.bookmarks?.open() },
      { id: 'new-window', name: 'New Window', category: 'Browser', icon: '🪟', shortcut: 'Ctrl+N', action: () => window.electronAPI?.window?.create() },
      { id: 'incognito', name: 'Incognito Window', category: 'Browser', icon: '🕵️', shortcut: 'Ctrl+Shift+N', action: () => window.electronAPI?.window?.createIncognito() },
      { id: 'clear-data', name: 'Clear Browsing Data', category: 'Browser', icon: '🗑️', shortcut: 'Ctrl+Shift+Delete', action: () => window.electronAPI?.privacy?.clearData() },
    ];
  }

  toggle() { this.isOpen ? this.close() : this.open(); }
  open() {
    this.isOpen = true;
    this.container.classList.add('open');
    this.input.value = '';
    this.input.focus();
    this.selectedIndex = 0;
    this.onInput();
  }
  close() {
    this.isOpen = false;
    this.container.classList.remove('open');
    this.input.value = '';
    this.results = [];
    this.render();
  }
  onInput() {
    const query = this.input.value.toLowerCase().trim();
    this.results = this.search(query);
    this.selectedIndex = 0;
    this.render();
  }
  onKeydown(e) {
    if (e.key === 'Escape') { this.close(); return; }
    if (e.key === 'ArrowDown') { e.preventDefault(); this.selectedIndex = Math.min(this.selectedIndex + 1, this.results.length - 1); this.render(); return; }
    if (e.key === 'ArrowUp') { e.preventDefault(); this.selectedIndex = Math.max(this.selectedIndex - 1, 0); this.render(); return; }
    if (e.key === 'Enter') { e.preventDefault(); if (this.results[this.selectedIndex]) this.execute(this.results[this.selectedIndex]); return; }
  }
  search(query) {
    if (!query) return this.commands.slice(0, 10);
    const results = [];
    this.commands.forEach(cmd => {
      const score = this.fuzzyScore(query, cmd.name.toLowerCase());
      if (score > 0) results.push({ ...cmd, score, type: 'command' });
    });
    if (window.tabs) {
      window.tabs.forEach(tab => {
        const score = this.fuzzyScore(query, (tab.title || '').toLowerCase());
        if (score > 0) results.push({ id: 'tab-' + tab.id, name: tab.title || tab.url, category: 'Open Tab', icon: '🌐', score, type: 'tab', action: () => window.electronAPI?.tabs?.activate(tab.id) });
      });
    }
    results.sort((a, b) => b.score - a.score);
    return results.slice(0, 15);
  }
  fuzzyScore(query, text) {
    let score = 0, qi = 0;
    for (let i = 0; i < text.length && qi < query.length; i++) {
      if (text[i] === query[qi]) { score += 10; if (i === qi) score += 5; qi++; }
    }
    if (qi < query.length) return 0;
    if (text === query) score += 50; else if (text.startsWith(query)) score += 30; else if (text.includes(query)) score += 20;
    return score;
  }
  render() {
    if (!this.isOpen) return;
    const html = this.results.map((r, i) => {
      return '<div class="cmd-item' + (i === this.selectedIndex ? ' selected' : '') + '" data-index="' + i + '"><span class="cmd-icon">' + r.icon + '</span><div class="cmd-info"><div class="cmd-name">' + r.name + '</div><div class="cmd-category">' + r.category + '</div></div>' + (r.shortcut ? '<kbd class="cmd-shortcut">' + r.shortcut + '</kbd>' : '') + '</div>';
    }).join('');
    this.resultsContainer.innerHTML = html || '<div class="cmd-empty">No results found</div>';
    this.resultsContainer.querySelectorAll('.cmd-item').forEach(item => {
      item.addEventListener('click', () => { const idx = parseInt(item.dataset.index); if (this.results[idx]) this.execute(this.results[idx]); });
      item.addEventListener('mouseenter', () => { this.selectedIndex = parseInt(item.dataset.index); this.render(); });
    });
  }
  execute(result) { if (result.action) result.action(); this.close(); }
}

document.addEventListener('DOMContentLoaded', () => { window.commandPalette = new CommandPalette(); });
