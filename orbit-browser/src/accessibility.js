/**
 * JARVIS Orbit — Accessibility Module
 * 
 * WCAG 2.1 AA compliance improvements:
 * - ARIA labels and roles
 * - Focus management
 * - Keyboard navigation
 * - Screen reader support
 * - High contrast mode
 * - Reduced motion support
 */

class Accessibility {
  constructor() {
    this.config = {
      focusTrap: true,
      skipLinks: true,
      ariaLive: true,
      keyboardNav: true,
      highContrast: false,
      reducedMotion: false,
      fontSize: 'normal', // small, normal, large, xlarge
    };
    
    this.focusHistory = [];
    this.shortcuts = new Map();
    
    this.init();
  }

  init() {
    // Detect user preferences
    this.detectPreferences();
    
    // Setup ARIA labels
    this.setupAriaLabels();
    
    // Setup focus management
    this.setupFocusManagement();
    
    // Setup keyboard navigation
    this.setupKeyboardNavigation();
    
    // Setup skip links
    if (this.config.skipLinks) {
      this.setupSkipLinks();
    }
    
    // Setup live regions
    if (this.config.ariaLive) {
      this.setupLiveRegions();
    }
    
    console.log('[A11Y] Accessibility module initialized');
  }

  // ── Preference Detection ────────────────────────────────────────
  
  detectPreferences() {
    // Reduced motion
    if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
      this.config.reducedMotion = true;
      document.documentElement.classList.add('reduced-motion');
    }
    
    // High contrast
    if (window.matchMedia('(prefers-contrast: high)').matches) {
      this.config.highContrast = true;
      document.documentElement.classList.add('high-contrast');
    }
    
    // Color scheme
    if (window.matchMedia('(prefers-color-scheme: light)').matches) {
      document.documentElement.dataset.theme = 'light';
    }
    
    // Listen for changes
    window.matchMedia('(prefers-reduced-motion: reduce)').addEventListener('change', (e) => {
      this.config.reducedMotion = e.matches;
      document.documentElement.classList.toggle('reduced-motion', e.matches);
    });
    
    window.matchMedia('(prefers-contrast: high)').addEventListener('change', (e) => {
      this.config.highContrast = e.matches;
      document.documentElement.classList.toggle('high-contrast', e.matches);
    });
  }

  // ── ARIA Labels ─────────────────────────────────────────────────
  
  setupAriaLabels() {
    // Add ARIA labels to interactive elements
    const ariaMap = {
      '#backBtn': { label: 'Go back', keyShortcuts: 'Alt+Left' },
      '#forwardBtn': { label: 'Go forward', keyShortcuts: 'Alt+Right' },
      '#reloadBtn': { label: 'Reload page', keyShortcuts: 'Ctrl+R' },
      '#homeBtn': { label: 'Go to homepage' },
      '#newTabBtn': { label: 'Open new tab', keyShortcuts: 'Ctrl+T' },
      '#omniInput': { label: 'Address bar', role: 'combobox' },
      '#jarvisBtn': { label: 'Toggle JARVIS sidebar', keyShortcuts: 'Ctrl+Shift+J' },
      '#menuBtn': { label: 'Open menu' },
      '#extBtn': { label: 'Extensions' },
      '#profileBtn': { label: 'Profile' },
      '#sbInput': { label: 'Ask JARVIS anything' },
      '#sbSend': { label: 'Send message' },
      '#findInput': { label: 'Find in page', role: 'searchbox' },
      '#cmdInput': { label: 'Search commands and tabs', role: 'combobox' },
      '#themeToggle': { label: 'Toggle dark/light theme' },
    };
    
    for (const [selector, attrs] of Object.entries(ariaMap)) {
      const el = document.querySelector(selector);
      if (el) {
        if (attrs.label) el.setAttribute('aria-label', attrs.label);
        if (attrs.role) el.setAttribute('role', attrs.role);
        if (attrs.keyShortcuts) el.setAttribute('aria-keyshortcuts', attrs.keyShortcuts);
      }
    }
    
    // Tab strip
    this.updateTabAriaLabels();
    
    // Add role landmarks
    this.setupLandmarks();
  }

  updateTabAriaLabels() {
    const tabs = document.querySelectorAll('.tab');
    tabs.forEach((tab, index) => {
      const title = tab.querySelector('.tab-title')?.textContent || 'Tab';
      const isActive = tab.classList.contains('active');
      
      tab.setAttribute('role', 'tab');
      tab.setAttribute('aria-label', `Tab ${index + 1}: ${title}`);
      tab.setAttribute('aria-selected', isActive);
      tab.setAttribute('tabindex', isActive ? '0' : '-1');
    });
    
    const tabStrip = document.getElementById('tabStrip');
    if (tabStrip) {
      tabStrip.setAttribute('role', 'tablist');
      tabStrip.setAttribute('aria-label', 'Open tabs');
    }
  }

  setupLandmarks() {
    // Main landmarks
    const landmarks = {
      'header.titlebar': 'banner',
      'div.toolbar': 'navigation',
      'div.body': 'main',
      'aside.sidebar': 'complementary',
      'footer.sb-composer': 'contentinfo',
    };
    
    for (const [selector, role] of Object.entries(landmarks)) {
      const el = document.querySelector(selector);
      if (el) {
        el.setAttribute('role', role);
      }
    }
    
    // Search landmark
    const omnibox = document.getElementById('omnibox');
    if (omnibox) {
      omnibox.setAttribute('role', 'search');
      omnibox.setAttribute('aria-label', 'Search and navigation');
    }
  }

  // ── Focus Management ────────────────────────────────────────────
  
  setupFocusManagement() {
    // Track focus history
    document.addEventListener('focusin', (e) => {
      this.focusHistory.push(e.target);
      if (this.focusHistory.length > 50) {
        this.focusHistory.shift();
      }
    });
    
    // Focus visible indicator
    document.addEventListener('keydown', (e) => {
      if (e.key === 'Tab') {
        document.body.classList.add('keyboard-nav');
      }
    });
    
    document.addEventListener('mousedown', () => {
      document.body.classList.remove('keyboard-nav');
    });
    
    // Focus trap for modals
    this.setupFocusTraps();
  }

  setupFocusTraps() {
    const modals = document.querySelectorAll('.modal-bg, .cmd-palette-bg');
    
    modals.forEach(modal => {
      modal.addEventListener('keydown', (e) => {
        if (e.key === 'Tab') {
          this.trapFocus(modal, e);
        }
      });
    });
  }

  trapFocus(container, event) {
    const focusable = container.querySelectorAll(
      'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])'
    );
    
    const first = focusable[0];
    const last = focusable[focusable.length - 1];
    
    if (event.shiftKey) {
      if (document.activeElement === first) {
        last.focus();
        event.preventDefault();
      }
    } else {
      if (document.activeElement === last) {
        first.focus();
        event.preventDefault();
      }
    }
  }

  focusElement(selector) {
    const el = document.querySelector(selector);
    if (el) {
      el.focus();
      el.scrollIntoView({ behavior: 'smooth', block: 'center' });
    }
  }

  // ── Keyboard Navigation ─────────────────────────────────────────
  
  setupKeyboardNavigation() {
    // Arrow key navigation for tabs
    document.addEventListener('keydown', (e) => {
      if (e.target.closest('.tab-strip') || e.target.closest('.tab-strip-vertical')) {
        this.handleTabNavigation(e);
      }
      
      // Arrow key navigation for lists
      if (e.target.closest('.cmd-results, .dsh-panel')) {
        this.handleListNavigation(e);
      }
    });
  }

  handleTabNavigation(e) {
    const tabs = Array.from(document.querySelectorAll('.tab'));
    const currentIndex = tabs.indexOf(document.activeElement);
    
    if (currentIndex === -1) return;
    
    let newIndex;
    
    switch (e.key) {
      case 'ArrowRight':
      case 'ArrowDown':
        newIndex = (currentIndex + 1) % tabs.length;
        break;
      case 'ArrowLeft':
      case 'ArrowUp':
        newIndex = (currentIndex - 1 + tabs.length) % tabs.length;
        break;
      case 'Home':
        newIndex = 0;
        break;
      case 'End':
        newIndex = tabs.length - 1;
        break;
      default:
        return;
    }
    
    e.preventDefault();
    tabs[newIndex].focus();
    tabs[newIndex].click();
  }

  handleListNavigation(e) {
    const items = Array.from(e.target.closest('.cmd-results, .dsh-panel').querySelectorAll('.cmd-item, .dsh-model, .dsh-command'));
    const currentIndex = items.indexOf(document.activeElement);
    
    if (currentIndex === -1 && items.length > 0) {
      items[0].focus();
      return;
    }
    
    let newIndex;
    
    switch (e.key) {
      case 'ArrowDown':
        newIndex = Math.min(currentIndex + 1, items.length - 1);
        break;
      case 'ArrowUp':
        newIndex = Math.max(currentIndex - 1, 0);
        break;
      case 'Enter':
        document.activeElement.click();
        return;
      default:
        return;
    }
    
    e.preventDefault();
    items[newIndex].focus();
  }

  // ── Skip Links ──────────────────────────────────────────────────
  
  setupSkipLinks() {
    const skipLinks = document.createElement('div');
    skipLinks.className = 'skip-links';
    skipLinks.innerHTML = `
      <a href="#omniInput" class="skip-link">Skip to address bar</a>
      <a href="#contentArea" class="skip-link">Skip to content</a>
      <a href="#sidebar" class="skip-link">Skip to JARVIS</a>
    `;
    
    document.body.insertBefore(skipLinks, document.body.firstChild);
    
    // Style skip links
    const style = document.createElement('style');
    style.textContent = `
      .skip-links {
        position: absolute;
        top: -40px;
        left: 0;
        z-index: 10000;
      }
      .skip-link {
        position: absolute;
        top: 0;
        left: 0;
        background: var(--jb-paper);
        color: var(--jb-void);
        padding: 8px 16px;
        text-decoration: none;
        font-weight: 500;
        transform: translateY(-100%);
        transition: transform 0.2s;
      }
      .skip-link:focus {
        transform: translateY(0);
      }
    `;
    document.head.appendChild(style);
  }

  // ── Live Regions ────────────────────────────────────────────────
  
  setupLiveRegions() {
    // Create live region for announcements
    const liveRegion = document.createElement('div');
    liveRegion.id = 'a11y-live';
    liveRegion.setAttribute('role', 'status');
    liveRegion.setAttribute('aria-live', 'polite');
    liveRegion.setAttribute('aria-atomic', 'true');
    liveRegion.className = 'sr-only';
    document.body.appendChild(liveRegion);
    
    // Style screen reader only
    const style = document.createElement('style');
    style.textContent = `
      .sr-only {
        position: absolute;
        width: 1px;
        height: 1px;
        padding: 0;
        margin: -1px;
        overflow: hidden;
        clip: rect(0, 0, 0, 0);
        white-space: nowrap;
        border: 0;
      }
    `;
    document.head.appendChild(style);
  }

  announce(message, priority = 'polite') {
    const liveRegion = document.getElementById('a11y-live');
    if (liveRegion) {
      liveRegion.setAttribute('aria-live', priority);
      liveRegion.textContent = message;
      
      // Clear after announcement
      setTimeout(() => {
        liveRegion.textContent = '';
      }, 1000);
    }
  }

  // ── Font Size ───────────────────────────────────────────────────
  
  setFontSize(size) {
    this.config.fontSize = size;
    
    const sizes = {
      small: '12px',
      normal: '14px',
      large: '16px',
      xlarge: '18px',
    };
    
    document.documentElement.style.fontSize = sizes[size] || sizes.normal;
    localStorage.setItem('a11y-font-size', size);
  }

  // ── High Contrast ───────────────────────────────────────────────
  
  toggleHighContrast() {
    this.config.highContrast = !this.config.highContrast;
    document.documentElement.classList.toggle('high-contrast', this.config.highContrast);
    localStorage.setItem('a11y-high-contrast', this.config.highContrast);
  }

  // ── Reduced Motion ──────────────────────────────────────────────
  
  toggleReducedMotion() {
    this.config.reducedMotion = !this.config.reducedMotion;
    document.documentElement.classList.toggle('reduced-motion', this.config.reducedMotion);
    localStorage.setItem('a11y-reduced-motion', this.config.reducedMotion);
  }

  // ── Status ──────────────────────────────────────────────────────
  
  getStatus() {
    return {
      ...this.config,
      focusHistoryLength: this.focusHistory.length,
      shortcutsRegistered: this.shortcuts.size,
    };
  }
}

// Export
window.Accessibility = Accessibility;
window.accessibility = new Accessibility();
