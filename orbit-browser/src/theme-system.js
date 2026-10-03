/**
 * JARVIS Orbit — Theme System
 * Vivaldi-style theme customization with dark/light/custom themes
 */
class ThemeSystem {
  constructor() {
    this.currentTheme = 'dark';
    this.themes = this.getThemes();
    this.accentColor = '#4285f4';
    this.init();
  }

  init() {
    // Load saved theme
    this.loadTheme();
    
    // Apply theme
    this.applyTheme(this.currentTheme);
    
    // Setup theme toggle
    this.setupThemeToggle();
  }

  getThemes() {
    return {
      dark: {
        name: 'Dark',
        colors: {
          bg: '#1a1a1a',
          surface: '#2d2d2d',
          text: '#ffffff',
          textSecondary: '#a0a0a0',
          border: '#404040',
          accent: '#4285f4'
        }
      },
      light: {
        name: 'Light',
        colors: {
          bg: '#ffffff',
          surface: '#f5f5f5',
          text: '#1a1a1a',
          textSecondary: '#666666',
          border: '#e0e0e0',
          accent: '#4285f4'
        }
      },
      midnight: {
        name: 'Midnight',
        colors: {
          bg: '#0d1117',
          surface: '#161b22',
          text: '#c9d1d9',
          textSecondary: '#8b949e',
          border: '#30363d',
          accent: '#58a6ff'
        }
      },
      solarized: {
        name: 'Solarized Dark',
        colors: {
          bg: '#002b36',
          surface: '#073642',
          text: '#839496',
          textSecondary: '#657b83',
          border: '#586e75',
          accent: '#268bd2'
        }
      },
      nord: {
        name: 'Nord',
        colors: {
          bg: '#2e3440',
          surface: '#3b4252',
          text: '#eceff4',
          textSecondary: '#d8dee9',
          border: '#4c566a',
          accent: '#88c0d0'
        }
      },
      dracula: {
        name: 'Dracula',
        colors: {
          bg: '#282a36',
          surface: '#44475a',
          text: '#f8f8f2',
          textSecondary: '#6272a4',
          border: '#6272a4',
          accent: '#bd93f9'
        }
      }
    };
  }

  applyTheme(themeId) {
    const theme = this.themes[themeId];
    if (!theme) return;

    this.currentTheme = themeId;
    document.documentElement.setAttribute('data-theme', themeId);
    
    // Apply CSS variables
    const root = document.documentElement;
    Object.entries(theme.colors).forEach(([key, value]) => {
      root.style.setProperty(`--theme-${key}`, value);
    });

    // Save theme
    localStorage.setItem('orbit-theme', themeId);
  }

  setAccentColor(color) {
    this.accentColor = color;
    document.documentElement.style.setProperty('--theme-accent', color);
    localStorage.setItem('orbit-accent', color);
  }

  loadTheme() {
    const savedTheme = localStorage.getItem('orbit-theme') || 'dark';
    const savedAccent = localStorage.getItem('orbit-accent');
    
    if (this.themes[savedTheme]) {
      this.currentTheme = savedTheme;
    }
    
    if (savedAccent) {
      this.accentColor = savedAccent;
    }
  }

  setupThemeToggle() {
    // Create theme toggle button
    const toggle = document.createElement('button');
    toggle.className = 'theme-toggle';
    toggle.innerHTML = `
      <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
        <circle cx="8" cy="8" r="4" stroke="currentColor" stroke-width="1.5"/>
        <path d="M8 1v2M8 13v2M1 8h2M13 8h2M3.05 3.05l1.41 1.41M11.54 11.54l1.41 1.41M3.05 12.95l1.41-1.41M11.54 4.46l1.41-1.41" stroke="currentColor" stroke-width="1.5"/>
      </svg>
    `;
    toggle.title = 'Toggle theme';
    
    // Add to toolbar
    document.querySelector('.toolbar')?.appendChild(toggle);
    
    // Toggle theme on click
    toggle.addEventListener('click', () => {
      const themes = Object.keys(this.themes);
      const currentIndex = themes.indexOf(this.currentTheme);
      const nextIndex = (currentIndex + 1) % themes.length;
      this.applyTheme(themes[nextIndex]);
    });
  }

  getThemes() {
    return this.themes;
  }

  getCurrentTheme() {
    return this.currentTheme;
  }

  getAccentColor() {
    return this.accentColor;
  }
}

document.addEventListener('DOMContentLoaded', () => { window.themeSystem = new ThemeSystem(); });
