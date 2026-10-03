/**
 * JARVIS Orbit — Session Manager
 * Vivaldi-style session management with auto-save and restore
 */
class SessionManager {
  constructor() {
    this.sessions = new Map();
    this.autoSaveInterval = null;
    this.currentSession = null;
    this.init();
  }

  init() {
    // Auto-save every 5 minutes
    this.autoSaveInterval = setInterval(() => this.autoSave(), 5 * 60 * 1000);
    // Save on close
    window.addEventListener('beforeunload', () => this.saveCurrentSession());
    // Load saved sessions
    this.loadSessions();
  }

  createSession(name) {
    const id = 'session-' + Date.now();
    const session = {
      id,
      name: name || 'Session ' + (this.sessions.size + 1),
      tabs: [],
      createdAt: Date.now(),
      lastModified: Date.now()
    };
    this.sessions.set(id, session);
    this.currentSession = id;
    this.saveSessions();
    return session;
  }

  saveCurrentSession() {
    if (!this.currentSession) return;
    const session = this.sessions.get(this.currentSession);
    if (!session) return;
    // Get current tabs from the browser
    session.tabs = window.tabs || [];
    session.lastModified = Date.now();
    this.saveSessions();
  }

  restoreSession(sessionId) {
    const session = this.sessions.get(sessionId);
    if (!session) return false;
    // Restore tabs
    session.tabs.forEach(tab => {
      window.electronAPI?.tabs?.create(tab.url);
    });
    this.currentSession = sessionId;
    return true;
  }

  deleteSession(sessionId) {
    this.sessions.delete(sessionId);
    this.saveSessions();
  }

  renameSession(sessionId, name) {
    const session = this.sessions.get(sessionId);
    if (session) {
      session.name = name;
      this.saveSessions();
    }
  }

  getSessions() {
    return Array.from(this.sessions.values()).sort((a, b) => b.lastModified - a.lastModified);
  }

  autoSave() {
    this.saveCurrentSession();
  }

  saveSessions() {
    const data = {};
    this.sessions.forEach((session, id) => {
      data[id] = session;
    });
    localStorage.setItem('orbit-sessions', JSON.stringify(data));
  }

  loadSessions() {
    try {
      const data = JSON.parse(localStorage.getItem('orbit-sessions') || '{}');
      Object.entries(data).forEach(([id, session]) => {
        this.sessions.set(id, session);
      });
    } catch (e) {
      console.error('Failed to load sessions:', e);
    }
  }
}

document.addEventListener('DOMContentLoaded', () => { window.sessionManager = new SessionManager(); });
