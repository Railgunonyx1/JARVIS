/**
 * JARVIS Orbit — Keyboard Shortcuts Manager
 * Customizable keyboard shortcuts with conflict detection
 */
class KeyboardShortcuts {
  constructor() {
    this.shortcuts = new Map();
    this.conflicts = [];
    this.customShortcuts = this.loadCustomShortcuts();
    this.init();
  }

  init() {
    this.registerDefaultShortcuts();
    this.setupGlobalListener();
  }

  registerDefaultShortcuts() {
    // Navigation
    this.register('new-tab', 'Ctrl+T', () => window.electronAPI?.tabs?.create());
    this.register('close-tab', 'Ctrl+W', () => window.electronAPI?.tabs?.closeActive());
    this.register('next-tab', 'Ctrl+Tab', () => window.electronAPI?.tabs?.next());
    this.register('prev-tab', 'Ctrl+Shift+Tab', () => window.electronAPI?.tabs?.previous());
    this.register('reopen-tab', 'Ctrl+Shift+T', () => window.electronAPI?.tabs?.reopen());
    
    // Address bar
    this.register('focus-address', 'Ctrl+L', () => document.querySelector('.omnibox input')?.focus());
    this.register('command-palette', 'Ctrl+K', () => window.commandPalette?.toggle());
    
    // Page actions
    this.register('reload', 'Ctrl+R', () => window.electronAPI?.page?.reload());
    this.register('hard-reload', 'Ctrl+Shift+R', () => window.electronAPI?.page?.hardReload());
    this.register('stop', 'Escape', () => window.electronAPI?.page?.stop());
    this.register('find', 'Ctrl+F', () => this.toggleFindBar());
    this.register('find-next', 'F3', () => window.electronAPI?.page?.findNext());
    this.register('find-prev', 'Shift+F3', () => window.electronAPI?.page?.findPrevious());
    
    // Zoom
    this.register('zoom-in', 'Ctrl+=', () => window.electronAPI?.page?.zoomIn());
    this.register('zoom-out', 'Ctrl+-', () => window.electronAPI?.page?.zoomOut());
    this.register('zoom-reset', 'Ctrl+0', () => window.electronAPI?.page?.zoomReset());
    
    // View
    this.register('fullscreen', 'F11', () => window.electronAPI?.page?.toggleFullscreen());
    this.register('devtools', 'F12', () => window.electronAPI?.page?.toggleDevTools());
    this.register('sidebar', 'Ctrl+Shift+J', () => window.jarvis?.toggleSidebar());
    this.register('vertical-tabs', 'Ctrl+Shift+E', () => window.verticalTabs?.toggle());
    
    // History
    this.register('back', 'Alt+Left', () => window.electronAPI?.page?.goBack());
    this.register('forward', 'Alt+Right', () => window.electronAPI?.page?.goForward());
    
    // JARVIS
    this.register('jarvis-focus', 'Ctrl+Shift+Space', () => window.jarvis?.focusChat());
    this.register('jarvis-task', 'Ctrl+Shift+A', () => window.jarvis?.createTask());
  }

  register(id, keys, callback) {
    // Check for conflicts
    const existing = this.shortcuts.get(keys);
    if (existing) {
      this.conflicts.push({ keys, existing: existing.id, new: id });
      console.warn(`Shortcut conflict: ${keys} already registered for ${existing.id}`);
    }
    
    this.shortcuts.set(keys, { id, callback });
  }

  unregister(keys) {
    this.shortcuts.delete(keys);
  }

  setupGlobalListener() {
    document.addEventListener('keydown', (e) => {
      const key = this.getKeyString(e);
      const shortcut = this.shortcuts.get(key);
      
      if (shortcut) {
        // Don't trigger if typing in an input
        if (this.isInputFocused() && !this.isInputShortcut(key)) {
          return;
        }
        
        e.preventDefault();
        shortcut.callback();
      }
    });
  }

  getKeyString(e) {
    const parts = [];
    if (e.ctrlKey) parts.push('Ctrl');
    if (e.shiftKey) parts.push('Shift');
    if (e.altKey) parts.push('Alt');
    if (e.metaKey) parts.push('Cmd');
    
    let key = e.key;
    if (key === ' ') key = 'Space';
    else if (key === 'ArrowUp') key = 'Up';
    else if (key === 'ArrowDown') key = 'Down';
    else if (key === 'ArrowLeft') key = 'Left';
    else if (key === 'ArrowRight') key = 'Right';
    else if (key === 'Escape') key = 'Esc';
    
    parts.push(key);
    return parts.join('+');
  }

  isInputFocused() {
    const active = document.activeElement;
    return active && (active.tagName === 'INPUT' || active.tagName === 'TEXTAREA' || active.isContentEditable);
  }

  isInputShortcut(key) {
    const inputShortcuts = ['Ctrl+C', 'Ctrl+V', 'Ctrl+X', 'Ctrl+A', 'Ctrl+Z', 'Ctrl+Y'];
    return inputShortcuts.includes(key);
  }

  toggleFindBar() {
    const findBar = document.querySelector('.find-bar');
    if (findBar) {
      findBar.style.display = findBar.style.display === 'none' ? 'flex' : 'none';
      if (findBar.style.display === 'flex') {
        findBar.querySelector('input')?.focus();
      }
    }
  }

  loadCustomShortcuts() {
    try {
      return JSON.parse(localStorage.getItem('orbit-shortcuts') || '{}');
    } catch {
      return {};
    }
  }

  saveCustomShortcuts() {
    localStorage.setItem('orbit-shortcuts', JSON.stringify(this.customShortcuts));
  }

  customizeShortcut(id, newKeys) {
    this.customShortcuts[id] = newKeys;
    this.saveCustomShortcuts();
    // Re-register with new keys
    const existing = Array.from(this.shortcuts.values()).find(s => s.id === id);
    if (existing) {
      this.unregister(newKeys); // Remove old binding
      this.register(id, newKeys, existing.callback);
    }
  }

  getShortcuts() {
    return Array.from(this.shortcuts.entries()).map(([keys, { id }]) => ({ id, keys }));
  }

  getConflicts() {
    return this.conflicts;
  }
}

document.addEventListener('DOMContentLoaded', () => { window.keyboardShortcuts = new KeyboardShortcuts(); });
