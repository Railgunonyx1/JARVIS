/**
 * JARVIS Orbit — JARVIS Command Bar
 * Quick access to JARVIS commands from the sidebar
 */
class JarvisCommandBar {
  constructor() {
    this.commands = this.getCommands();
    this.history = [];
    this.init();
  }

  init() {
    this.container = document.querySelector('.jarvis-command-bar');
    if (!this.container) return;

    this.input = this.container.querySelector('input');
    this.suggestions = this.container.querySelector('.jarvis-suggestions');
    
    this.input.addEventListener('input', () => this.onInput());
    this.input.addEventListener('keydown', (e) => this.onKeydown(e));
    
    // Load command history
    this.loadHistory();
  }

  getCommands() {
    return [
      { id: 'chat', name: 'Chat', prefix: '/', description: 'Interactive chat with JARVIS', action: (args) => window.jarvis?.chat(args) },
      { id: 'task', name: 'Task', prefix: '/task', description: 'Create an autonomous task', action: (args) => window.jarvis?.createTask(args) },
      { id: 'research', name: 'Research', prefix: '/research', description: 'Research a topic', action: (args) => window.jarvis?.research(args) },
      { id: 'summarize', name: 'Summarize', prefix: '/summarize', description: 'Summarize current page', action: () => window.jarvis?.summarize() },
      { id: 'remember', name: 'Remember', prefix: '/remember', description: 'Save to memory', action: (args) => window.jarvis?.remember(args) },
      { id: 'forget', name: 'Forget', prefix: '/forget', description: 'Forget from memory', action: (args) => window.jarvis?.forget(args) },
      { id: 'status', name: 'Status', prefix: '/status', description: 'System status', action: () => window.jarvis?.status() },
      { id: 'models', name: 'Models', prefix: '/models', description: 'Switch model', action: (args) => window.jarvis?.switchModel(args) },
      { id: 'help', name: 'Help', prefix: '/help', description: 'Show available commands', action: () => this.showHelp() },
      { id: 'clear', name: 'Clear', prefix: '/clear', description: 'Clear chat history', action: () => window.jarvis?.clearHistory() },
      { id: 'export', name: 'Export', prefix: '/export', description: 'Export chat history', action: () => window.jarvis?.exportHistory() },
      { id: 'settings', name: 'Settings', prefix: '/settings', description: 'Open JARVIS settings', action: () => window.jarvis?.openSettings() },
    ];
  }

  onInput() {
    const value = this.input.value.trim();
    if (!value.startsWith('/')) {
      this.suggestions.style.display = 'none';
      return;
    }

    const matches = this.commands.filter(cmd => 
      cmd.prefix.toLowerCase().startsWith(value.toLowerCase())
    );

    if (matches.length > 0) {
      this.suggestions.innerHTML = matches.map(cmd => `
        <div class="jarvis-suggestion" data-command="${cmd.id}">
          <span class="suggestion-name">${cmd.name}</span>
          <span class="suggestion-desc">${cmd.description}</span>
        </div>
      `).join('');
      this.suggestions.style.display = 'block';

      this.suggestions.querySelectorAll('.jarvis-suggestion').forEach(el => {
        el.addEventListener('click', () => {
          const cmd = this.commands.find(c => c.id === el.dataset.command);
          if (cmd) {
            this.input.value = cmd.prefix + ' ';
            this.suggestions.style.display = 'none';
            this.input.focus();
          }
        });
      });
    } else {
      this.suggestions.style.display = 'none';
    }
  }

  onKeydown(e) {
    if (e.key === 'Enter') {
      const value = this.input.value.trim();
      if (!value) return;

      if (value.startsWith('/')) {
        this.executeCommand(value);
      } else {
        // Regular chat message
        window.jarvis?.chat(value);
      }

      // Add to history
      this.addToHistory(value);
      this.input.value = '';
      this.suggestions.style.display = 'none';
    }

    if (e.key === 'Escape') {
      this.input.value = '';
      this.suggestions.style.display = 'none';
    }
  }

  executeCommand(input) {
    const parts = input.split(' ');
    const command = parts[0].toLowerCase();
    const args = parts.slice(1).join(' ');

    const cmd = this.commands.find(c => c.prefix.toLowerCase() === command);
    if (cmd) {
      cmd.action(args);
    } else {
      window.jarvis?.chat(input);
    }
  }

  addToHistory(command) {
    this.history.unshift(command);
    if (this.history.length > 50) this.history.pop();
    this.saveHistory();
  }

  loadHistory() {
    try {
      this.history = JSON.parse(localStorage.getItem('jarvis-command-history') || '[]');
    } catch {
      this.history = [];
    }
  }

  saveHistory() {
    localStorage.setItem('jarvis-command-history', JSON.stringify(this.history));
  }

  showHelp() {
    const helpText = this.commands.map(cmd => 
      `${cmd.prefix} - ${cmd.description}`
    ).join('\n');
    
    window.jarvis?.addMessage('system', `Available commands:\n${helpText}`);
  }
}

document.addEventListener('DOMContentLoaded', () => { window.jarvisCommandBar = new JarvisCommandBar(); });
