/**
 * JARVIS Orbit — JARVIS Integration Module
 * 
 * Enhances browser-JARVIS communication with:
 * - Agent workspace management
 * - Task progress tracking
 * - Notification system
 * - Quick actions menu
 * - Agent-owned tab indicators
 */

class JarvisIntegration {
  constructor() {
    this.agents = new Map();
    this.tasks = new Map();
    this.notifications = [];
    this.maxNotifications = 50;
    this.quickActions = [
      { id: 'summarize', label: 'Summarize Page', icon: '📋', shortcut: 'Ctrl+Shift+M' },
      { id: 'research', label: 'Research Topic', icon: '🔍', shortcut: 'Ctrl+Shift+R' },
      { id: 'explain', label: 'Explain Code', icon: '💡', shortcut: 'Ctrl+Shift+E' },
      { id: 'translate', label: 'Translate', icon: '🌐', shortcut: 'Ctrl+Shift+T' },
      { id: 'extract', label: 'Extract Data', icon: '📊', shortcut: 'Ctrl+Shift+X' },
      { id: 'compare', label: 'Compare Sources', icon: '⚖️', shortcut: 'Ctrl+Shift+C' },
    ];
    this.init();
  }

  init() {
    this.setupEventListeners();
    this.loadPersistedState();
  }

  setupEventListeners() {
    // Listen for JARVIS events
    if (window.orbit?.jarvis) {
      window.orbit.jarvis.onAgentEvent((event) => this.handleAgentEvent(event));
      window.orbit.jarvis.onStatus((status) => this.handleStatusChange(status));
    }

    // Keyboard shortcuts for quick actions
    document.addEventListener('keydown', (e) => {
      if (e.ctrlKey && e.shiftKey) {
        const action = this.quickActions.find(a => 
          a.shortcut === `Ctrl+Shift+${e.key.toUpperCase()}`
        );
        if (action) {
          e.preventDefault();
          this.executeQuickAction(action.id);
        }
      }
    });
  }

  loadPersistedState() {
    try {
      const saved = localStorage.getItem('jarvis-state');
      if (saved) {
        const state = JSON.parse(saved);
        this.agents = new Map(state.agents || []);
        this.tasks = new Map(state.tasks || []);
      }
    } catch (e) {
      console.warn('[JARVIS] Failed to load persisted state:', e);
    }
  }

  persistState() {
    try {
      localStorage.setItem('jarvis-state', JSON.stringify({
        agents: Array.from(this.agents.entries()),
        tasks: Array.from(this.tasks.entries()),
      }));
    } catch (e) {
      console.warn('[JARVIS] Failed to persist state:', e);
    }
  }

  // ── Agent Management ────────────────────────────────────────────
  
  createAgent(config = {}) {
    const id = `agent-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`;
    const agent = {
      id,
      name: config.name || `Agent ${this.agents.size + 1}`,
      status: 'idle',
      created: Date.now(),
      lastActive: Date.now(),
      tabId: null,
      taskCount: 0,
      capabilities: config.capabilities || ['browse', 'read', 'interact'],
      ...config,
    };
    
    this.agents.set(id, agent);
    this.persistState();
    this.notify('agent-created', { agent });
    return agent;
  }

  updateAgent(id, updates) {
    const agent = this.agents.get(id);
    if (!agent) return null;
    
    Object.assign(agent, updates, { lastActive: Date.now() });
    this.agents.set(id, agent);
    this.persistState();
    this.notify('agent-updated', { agent });
    return agent;
  }

  deleteAgent(id) {
    if (!this.agents.has(id)) return false;
    this.agents.delete(id);
    this.persistState();
    this.notify('agent-deleted', { agentId: id });
    return true;
  }

  getAgent(id) {
    return this.agents.get(id);
  }

  listAgents() {
    return Array.from(this.agents.values());
  }

  // ── Task Management ─────────────────────────────────────────────
  
  createTask(agentId, config = {}) {
    const taskId = `task-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`;
    const task = {
      id: taskId,
      agentId,
      title: config.title || 'New Task',
      description: config.description || '',
      status: 'pending',
      progress: 0,
      created: Date.now(),
      updated: Date.now(),
      steps: config.steps || [],
      currentStep: 0,
      result: null,
      error: null,
    };
    
    this.tasks.set(taskId, task);
    
    // Update agent task count
    const agent = this.agents.get(agentId);
    if (agent) {
      agent.taskCount++;
      agent.status = 'working';
      this.agents.set(agentId, agent);
    }
    
    this.persistState();
    this.notify('task-created', { task });
    return task;
  }

  updateTask(id, updates) {
    const task = this.tasks.get(id);
    if (!task) return null;
    
    Object.assign(task, updates, { updated: Date.now() });
    this.tasks.set(id, task);
    
    // Update agent status if task completed/failed
    if (updates.status === 'completed' || updates.status === 'failed') {
      const agent = this.agents.get(task.agentId);
      if (agent) {
        agent.status = updates.status === 'completed' ? 'idle' : 'error';
        this.agents.set(task.agentId, agent);
      }
    }
    
    this.persistState();
    this.notify('task-updated', { task });
    return task;
  }

  getTask(id) {
    return this.tasks.get(id);
  }

  listTasks(agentId = null) {
    const tasks = Array.from(this.tasks.values());
    return agentId ? tasks.filter(t => t.agentId === agentId) : tasks;
  }

  // ── Notification System ─────────────────────────────────────────
  
  notify(type, data) {
    const notification = {
      id: `notif-${Date.now()}`,
      type,
      data,
      timestamp: Date.now(),
      read: false,
    };
    
    this.notifications.unshift(notification);
    if (this.notifications.length > this.maxNotifications) {
      this.notifications.pop();
    }
    
    this.renderNotification(notification);
    return notification;
  }

  renderNotification(notification) {
    const container = document.getElementById('toastContainer');
    if (!container) return;
    
    const { type, data } = notification;
    let title = 'JARVIS';
    let message = '';
    let icon = 'ℹ️';
    let cssClass = 'info';
    
    switch (type) {
      case 'agent-created':
        title = 'Agent Created';
        message = `${data.agent.name} is ready`;
        icon = '🤖';
        cssClass = 'ok';
        break;
      case 'agent-updated':
        title = 'Agent Updated';
        message = `${data.agent.name} status: ${data.agent.status}`;
        icon = '🔄';
        break;
      case 'agent-deleted':
        title = 'Agent Removed';
        message = 'Agent has been deleted';
        icon = '🗑️';
        break;
      case 'task-created':
        title = 'Task Started';
        message = data.task.title;
        icon = '📋';
        cssClass = 'ok';
        break;
      case 'task-updated':
        title = 'Task Updated';
        message = `${data.task.title}: ${data.task.status}`;
        icon = data.task.status === 'completed' ? '✅' : 
               data.task.status === 'failed' ? '❌' : '🔄';
        cssClass = data.task.status === 'completed' ? 'ok' : 
                   data.task.status === 'failed' ? 'err' : 'info';
        break;
      case 'status-change':
        title = 'JARVIS Status';
        message = data.ok ? 'Connected' : 'Disconnected';
        icon = data.ok ? '🟢' : '🔴';
        cssClass = data.ok ? 'ok' : 'warn';
        break;
    }
    
    // Use toast system
    if (window.showToast) {
      window.showToast(cssClass, title, message, 4000);
    }
  }

  getNotifications(limit = 20) {
    return this.notifications.slice(0, limit);
  }

  markNotificationRead(id) {
    const notif = this.notifications.find(n => n.id === id);
    if (notif) notif.read = true;
  }

  clearNotifications() {
    this.notifications = [];
  }

  // ── Quick Actions ───────────────────────────────────────────────
  
  async executeQuickAction(actionId, context = {}) {
    const action = this.quickActions.find(a => a.id === actionId);
    if (!action) return null;
    
    const currentUrl = context.url || window.location.href;
    const pageTitle = context.title || document.title;
    
    let prompt = '';
    switch (actionId) {
      case 'summarize':
        prompt = `Summarize the content of this page: ${pageTitle} (${currentUrl})`;
        break;
      case 'research':
        prompt = `Research this topic: ${context.topic || pageTitle}`;
        break;
      case 'explain':
        prompt = `Explain the code or content on this page`;
        break;
      case 'translate':
        prompt = `Translate the content to ${context.language || 'English'}`;
        break;
      case 'extract':
        prompt = `Extract key data from this page`;
        break;
      case 'compare':
        prompt = `Compare information from multiple sources`;
        break;
    }
    
    if (prompt && window.orbit?.jarvis) {
      window.orbit.jarvis.chat(prompt, 'quick-action');
      this.notify('quick-action', { action: actionId, prompt });
    }
    
    return { action, prompt };
  }

  // ── Event Handlers ──────────────────────────────────────────────
  
  handleAgentEvent(event) {
    const { agentId, state, data } = event;
    
    if (agentId) {
      this.updateAgent(agentId, { status: state });
    }
    
    this.notify('agent-event', event);
  }

  handleStatusChange(status) {
    this.notify('status-change', status);
  }

  // ── UI Helpers ──────────────────────────────────────────────────
  
  renderAgentPanel() {
    const agents = this.listAgents();
    const tasks = this.listTasks();
    
    let html = '<div class="jarvis-agents">';
    
    if (agents.length === 0) {
      html += `
        <div class="jarvis-empty">
          <div class="jarvis-empty-icon">🤖</div>
          <div class="jarvis-empty-text">No agents yet</div>
          <button class="jarvis-btn" onclick="window.jarvisIntegration.createAgent()">
            Create Agent
          </button>
        </div>
      `;
    } else {
      html += '<div class="jarvis-agent-list">';
      for (const agent of agents) {
        const agentTasks = this.listTasks(agent.id);
        const activeTask = agentTasks.find(t => t.status === 'running');
        
        html += `
          <div class="jarvis-agent" data-agent-id="${agent.id}">
            <div class="jarvis-agent-header">
              <div class="jarvis-agent-status ${agent.status}"></div>
              <div class="jarvis-agent-name">${this.escapeHtml(agent.name)}</div>
              <button class="jarvis-agent-menu" onclick="window.jarvisIntegration.showAgentMenu('${agent.id}')">⋯</button>
            </div>
            <div class="jarvis-agent-meta">
              ${agentTasks.length} tasks · ${agent.status}
            </div>
            ${activeTask ? `
              <div class="jarvis-agent-task">
                <div class="jarvis-task-title">${this.escapeHtml(activeTask.title)}</div>
                <div class="jarvis-task-progress">
                  <div class="jarvis-progress-bar" style="width: ${activeTask.progress}%"></div>
                </div>
              </div>
            ` : ''}
          </div>
        `;
      }
      html += '</div>';
      
      html += `
        <button class="jarvis-btn jarvis-btn-full" onclick="window.jarvisIntegration.createAgent()">
          + New Agent
        </button>
      `;
    }
    
    html += '</div>';
    return html;
  }

  escapeHtml(str) {
    const div = document.createElement('div');
    div.textContent = str;
    return div.innerHTML;
  }
}

// Export
window.JarvisIntegration = JarvisIntegration;
window.jarvisIntegration = new JarvisIntegration();
