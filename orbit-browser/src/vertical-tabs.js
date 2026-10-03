/**
 * JARVIS Orbit — Vertical Tabs
 * Edge-style vertical tab strip that can be toggled
 */
class VerticalTabs {
  constructor() {
    this.isEnabled = false;
    this.width = 240;
    this.isResizing = false;
    this.init();
  }

  init() {
    // Create vertical tab strip container
    this.container = document.createElement('div');
    this.container.className = 'vertical-tabs-container';
    this.container.style.display = 'none';
    document.querySelector('.browser-body')?.prepend(this.container);

    // Create resize handle
    this.resizeHandle = document.createElement('div');
    this.resizeHandle.className = 'vertical-tabs-resize';
    this.container.appendChild(this.resizeHandle);

    // Create tab list
    this.tabList = document.createElement('div');
    this.tabList.className = 'vertical-tabs-list';
    this.container.appendChild(this.tabList);

    // Create new tab button
    this.newTabBtn = document.createElement('button');
    this.newTabBtn.className = 'vertical-tabs-new';
    this.newTabBtn.innerHTML = '<svg width="14" height="14" viewBox="0 0 14 14" fill="none"><path d="M7 1v12M1 7h12" stroke="currentColor" stroke-width="1.5"/></svg>';
    this.newTabBtn.addEventListener('click', () => window.electronAPI?.tabs?.create());
    this.container.appendChild(this.newTabBtn);

    // Resize handling
    this.resizeHandle.addEventListener('mousedown', (e) => {
      this.isResizing = true;
      e.preventDefault();
    });
    document.addEventListener('mousemove', (e) => {
      if (!this.isResizing) return;
      this.width = Math.max(180, Math.min(400, e.clientX));
      this.container.style.width = this.width + 'px';
    });
    document.addEventListener('mouseup', () => { this.isResizing = false; });

    // Keyboard shortcut
    document.addEventListener('keydown', (e) => {
      if ((e.ctrlKey || e.metaKey) && e.shiftKey && e.key === 'E') {
        e.preventDefault();
        this.toggle();
      }
    });
  }

  toggle() {
    this.isEnabled ? this.disable() : this.enable();
  }

  enable() {
    this.isEnabled = true;
    this.container.style.display = 'flex';
    document.querySelector('.browser-body')?.classList.add('has-vertical-tabs');
    this.render();
  }

  disable() {
    this.isEnabled = false;
    this.container.style.display = 'none';
    document.querySelector('.browser-body')?.classList.remove('has-vertical-tabs');
  }

  render() {
    if (!this.isEnabled) return;
    const tabs = window.tabs || [];
    this.tabList.innerHTML = tabs.map(tab => `
      <div class="vertical-tab ${tab.active ? 'active' : ''} ${tab.audible ? 'audible' : ''}" data-tab-id="${tab.id}">
        <img class="vertical-tab-favicon" src="${tab.favicon || ''}" onerror="this.style.display='none'" />
        <span class="vertical-tab-title">${this.escapeHtml(tab.title || 'New Tab')}</span>
        <button class="vertical-tab-close" data-close="${tab.id}">×</button>
      </div>
    `).join('');

    // Event listeners
    this.tabList.querySelectorAll('.vertical-tab').forEach(el => {
      el.addEventListener('click', (e) => {
        if (e.target.classList.contains('vertical-tab-close')) {
          window.electronAPI?.tabs?.close(e.target.dataset.close);
        } else {
          window.electronAPI?.tabs?.activate(el.dataset.tabId);
        }
      });
      el.addEventListener('contextmenu', (e) => this.showContextMenu(e, el.dataset.tabId));
    });
  }

  showContextMenu(e, tabId) {
    e.preventDefault();
    // Context menu for vertical tabs
    const menu = document.createElement('div');
    menu.className = 'context-menu';
    menu.innerHTML = `
      <button data-action="close">Close Tab</button>
      <button data-action="close-others">Close Other Tabs</button>
      <button data-action="duplicate">Duplicate Tab</button>
      <button data-action="reload">Reload Tab</button>
    `;
    menu.style.left = e.clientX + 'px';
    menu.style.top = e.clientY + 'px';
    document.body.appendChild(menu);

    menu.querySelectorAll('button').forEach(btn => {
      btn.addEventListener('click', () => {
        const action = btn.dataset.action;
        if (action === 'close') window.electronAPI?.tabs?.close(tabId);
        else if (action === 'close-others') window.electronAPI?.tabs?.closeOthers(tabId);
        else if (action === 'duplicate') window.electronAPI?.tabs?.duplicate(tabId);
        else if (action === 'reload') window.electronAPI?.tabs?.reload(tabId);
        menu.remove();
      });
    });

    document.addEventListener('click', () => menu.remove(), { once: true });
  }

  escapeHtml(str) {
    const div = document.createElement('div');
    div.textContent = str;
    return div.innerHTML;
  }
}

document.addEventListener('DOMContentLoaded', () => { window.verticalTabs = new VerticalTabs(); });
