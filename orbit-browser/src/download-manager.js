/**
 * JARVIS Orbit — Download Manager
 * 
 * Full-featured download management:
 * - Progress tracking
 * - Pause/Resume/Cancel
 * - Speed calculation
 * - Agent approval for sensitive downloads
 * - Download history
 * - File type detection
 */

class DownloadManager {
  constructor() {
    this.config = {
      maxConcurrent: 3,
      autoRetry: true,
      maxRetries: 3,
      requireApproval: ['exe', 'msi', 'bat', 'cmd', 'ps1', 'sh'],
      savePath: '~/Downloads',
    };
    
    this.downloads = new Map();
    this.history = [];
    this.maxHistory = 100;
    this.queue = [];
    
    this.init();
  }

  init() {
    this.loadHistory();
    this.setupEventListeners();
    console.log('[DOWNLOAD] Download manager initialized');
  }

  setupEventListeners() {
    // Listen for download events from webview
    document.addEventListener('click', (e) => {
      const link = e.target.closest('a[href]');
      if (link) {
        const href = link.getAttribute('href');
        if (this.isDownloadLink(href)) {
          e.preventDefault();
          this.startDownload(href, link.download || '');
        }
      }
    });
  }

  // ── Download Management ─────────────────────────────────────────
  
  async startDownload(url, filename = '', options = {}) {
    const id = `download-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`;
    
    // Check if approval needed
    const ext = this.getFileExtension(url);
    if (this.config.requireApproval.includes(ext) && !options.approved) {
      const approved = await this.requestApproval(url, filename);
      if (!approved) {
        return { success: false, reason: 'denied' };
      }
    }
    
    const download = {
      id,
      url,
      filename: filename || this.generateFilename(url),
      status: 'pending',
      progress: 0,
      speed: 0,
      totalSize: 0,
      receivedSize: 0,
      startTime: Date.now(),
      estimatedTime: 0,
      retries: 0,
      error: null,
      metadata: {
        referrer: window.location.href,
        userAgent: navigator.userAgent,
      },
    };
    
    this.downloads.set(id, download);
    this.emit('download-started', download);
    
    // Start download
    this.processDownload(id);
    
    return { success: true, id, download };
  }

  async processDownload(id) {
    const download = this.downloads.get(id);
    if (!download) return;
    
    download.status = 'downloading';
    this.emit('download-progress', download);
    
    try {
      // Use fetch for download
      const response = await fetch(download.url, {
        headers: {
          'Accept': '*/*',
        },
      });
      
      if (!response.ok) {
        throw new Error(`HTTP ${response.status}: ${response.statusText}`);
      }
      
      // Get total size
      const contentLength = response.headers.get('content-length');
      download.totalSize = parseInt(contentLength) || 0;
      
      // Get content type
      const contentType = response.headers.get('content-type');
      download.contentType = contentType;
      
      // Read response
      const reader = response.body.getReader();
      const chunks = [];
      let received = 0;
      
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        
        chunks.push(value);
        received += value.length;
        
        // Update progress
        download.receivedSize = received;
        download.progress = download.totalSize > 0 
          ? Math.round((received / download.totalSize) * 100)
          : 0;
        
        // Calculate speed
        const elapsed = (Date.now() - download.startTime) / 1000;
        download.speed = received / elapsed;
        
        // Estimate time remaining
        if (download.totalSize > 0 && download.speed > 0) {
          download.estimatedTime = Math.round((download.totalSize - received) / download.speed);
        }
        
        this.emit('download-progress', download);
        
        // Check if paused
        if (download.status === 'paused') {
          await this.waitForResume(download);
        }
        
        // Check if cancelled
        if (download.status === 'cancelled') {
          reader.cancel();
          return;
        }
      }
      
      // Combine chunks
      const blob = new Blob(chunks);
      
      // Save file
      await this.saveFile(blob, download.filename);
      
      download.status = 'completed';
      download.progress = 100;
      download.endTime = Date.now();
      
      this.addToHistory(download);
      this.emit('download-completed', download);
      
      console.log(`[DOWNLOAD] Completed: ${download.filename}`);
      
    } catch (error) {
      console.error('[DOWNLOAD] Error:', error);
      
      download.error = error.message;
      
      // Auto retry
      if (this.config.autoRetry && download.retries < this.config.maxRetries) {
        download.retries++;
        download.status = 'retrying';
        this.emit('download-retrying', download);
        
        setTimeout(() => {
          this.processDownload(id);
        }, 1000 * download.retries);
      } else {
        download.status = 'failed';
        this.emit('download-failed', download);
      }
    }
  }

  async saveFile(blob, filename) {
    // Create download link
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  }

  // ── Download Controls ───────────────────────────────────────────
  
  pauseDownload(id) {
    const download = this.downloads.get(id);
    if (download && download.status === 'downloading') {
      download.status = 'paused';
      download.pauseTime = Date.now();
      this.emit('download-paused', download);
      return true;
    }
    return false;
  }

  resumeDownload(id) {
    const download = this.downloads.get(id);
    if (download && download.status === 'paused') {
      download.status = 'downloading';
      download.pauseTime = null;
      this.emit('download-resumed', download);
      return true;
    }
    return false;
  }

  cancelDownload(id) {
    const download = this.downloads.get(id);
    if (download) {
      download.status = 'cancelled';
      this.emit('download-cancelled', download);
      this.downloads.delete(id);
      return true;
    }
    return false;
  }

  retryDownload(id) {
    const download = this.downloads.get(id);
    if (download && download.status === 'failed') {
      download.retries = 0;
      download.error = null;
      this.processDownload(id);
      return true;
    }
    return false;
  }

  waitForResume(download) {
    return new Promise((resolve) => {
      const check = setInterval(() => {
        if (download.status !== 'paused') {
          clearInterval(check);
          resolve();
        }
      }, 100);
    });
  }

  // ── Approval Flow ───────────────────────────────────────────────
  
  async requestApproval(url, filename) {
    return new Promise((resolve) => {
      // Emit approval request
      this.emit('approval-request', {
        type: 'download',
        url,
        filename,
        callback: (approved) => {
          resolve(approved);
        },
      });
      
      // Auto-approve after 30 seconds for non-sensitive files
      setTimeout(() => {
        const ext = this.getFileExtension(url);
        if (!this.config.requireApproval.includes(ext)) {
          resolve(true);
        }
      }, 30000);
    });
  }

  // ── Helper Methods ──────────────────────────────────────────────
  
  isDownloadLink(url) {
    if (!url) return false;
    
    const downloadExtensions = [
      '.zip', '.rar', '.7z', '.tar', '.gz',
      '.exe', '.msi', '.dmg', '.pkg', '.deb', '.rpm',
      '.pdf', '.doc', '.docx', '.xls', '.xlsx', '.ppt', '.pptx',
      '.mp3', '.mp4', '.avi', '.mov', '.mkv', '.flv',
      '.jpg', '.jpeg', '.png', '.gif', '.svg', '.webp',
      '.iso', '.img',
    ];
    
    const ext = this.getFileExtension(url);
    return downloadExtensions.includes(ext);
  }

  getFileExtension(url) {
    try {
      const pathname = new URL(url).pathname;
      const ext = pathname.split('.').pop().toLowerCase();
      return ext ? `.${ext}` : '';
    } catch {
      return '';
    }
  }

  generateFilename(url) {
    try {
      const pathname = new URL(url).pathname;
      const filename = pathname.split('/').pop() || 'download';
      return decodeURIComponent(filename);
    } catch {
      return `download-${Date.now()}`;
    }
  }

  formatSpeed(bytesPerSecond) {
    if (bytesPerSecond < 1024) return `${bytesPerSecond} B/s`;
    if (bytesPerSecond < 1024 * 1024) return `${(bytesPerSecond / 1024).toFixed(1)} KB/s`;
    return `${(bytesPerSecond / (1024 * 1024)).toFixed(1)} MB/s`;
  }

  formatSize(bytes) {
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    if (bytes < 1024 * 1024 * 1024) return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
    return `${(bytes / (1024 * 1024 * 1024)).toFixed(2)} GB`;
  }

  formatTime(seconds) {
    if (seconds < 60) return `${seconds}s`;
    if (seconds < 3600) return `${Math.floor(seconds / 60)}m ${seconds % 60}s`;
    return `${Math.floor(seconds / 3600)}h ${Math.floor((seconds % 3600) / 60)}m`;
  }

  // ── History ─────────────────────────────────────────────────────
  
  addToHistory(download) {
    this.history.unshift({
      ...download,
      completedAt: Date.now(),
    });
    
    if (this.history.length > this.maxHistory) {
      this.history.pop();
    }
    
    this.saveHistory();
  }

  loadHistory() {
    try {
      const saved = localStorage.getItem('download-history');
      if (saved) {
        this.history = JSON.parse(saved);
      }
    } catch (e) {
      console.warn('[DOWNLOAD] Failed to load history:', e);
    }
  }

  saveHistory() {
    try {
      localStorage.setItem('download-history', JSON.stringify(this.history));
    } catch (e) {
      console.warn('[DOWNLOAD] Failed to save history:', e);
    }
  }

  clearHistory() {
    this.history = [];
    this.saveHistory();
  }

  // ── Event System ────────────────────────────────────────────────
  
  emit(event, data) {
    const customEvent = new CustomEvent('download-event', {
      detail: { type: event, data },
    });
    window.dispatchEvent(customEvent);
  }

  on(callback) {
    window.addEventListener('download-event', (e) => {
      callback(e.detail.type, e.detail.data);
    });
  }

  // ── Statistics ──────────────────────────────────────────────────
  
  getStats() {
    const active = Array.from(this.downloads.values());
    const downloading = active.filter(d => d.status === 'downloading');
    
    return {
      active: active.length,
      downloading: downloading.length,
      totalSpeed: downloading.reduce((sum, d) => sum + d.speed, 0),
      historyCount: this.history.length,
      totalDownloaded: this.history.reduce((sum, d) => sum + (d.receivedSize || 0), 0),
    };
  }

  // ── UI Rendering ────────────────────────────────────────────────
  
  renderDownloadsPage() {
    const active = Array.from(this.downloads.values());
    const history = this.history.slice(0, 20);
    
    let html = `
      <div class="sheet">
        <h1>Downloads</h1>
        <p class="sheet-lede">Agent-origin files wait for approval before they touch disk.</p>
    `;
    
    // Active downloads
    if (active.length > 0) {
      html += '<div class="group"><h2>Active</h2>';
      active.forEach(d => {
        html += `
          <div class="row" data-download-id="${d.id}">
            <div>
              <div class="name">${this.escapeHtml(d.filename)}</div>
              <div class="sub">${this.formatSpeed(d.speed)} · ${this.formatSize(d.receivedSize)}${d.totalSize > 0 ? ' / ' + this.formatSize(d.totalSize) : ''}</div>
            </div>
            <div class="download-progress">
              <div class="download-progress-bar" style="width: ${d.progress}%"></div>
            </div>
            <span class="meta">${d.progress}%</span>
            ${d.status === 'downloading' ? '<span class="chip ok">Downloading</span>' : ''}
            ${d.status === 'paused' ? '<span class="chip warn">Paused</span>' : ''}
            ${d.status === 'failed' ? '<span class="chip bad">Failed</span>' : ''}
            <div class="download-actions">
              ${d.status === 'downloading' ? '<button class="chip-btn" onclick="window.downloadManager.pauseDownload(\'' + d.id + '\')">Pause</button>' : ''}
              ${d.status === 'paused' ? '<button class="chip-btn" onclick="window.downloadManager.resumeDownload(\'' + d.id + '\')">Resume</button>' : ''}
              <button class="chip-btn" onclick="window.downloadManager.cancelDownload('${d.id}')">Cancel</button>
            </div>
          </div>
        `;
      });
      html += '</div>';
    }
    
    // History
    if (history.length > 0) {
      html += '<div class="group"><h2>History</h2>';
      history.forEach(d => {
        const timeAgo = this.formatTimeAgo(d.completedAt);
        html += `
          <div class="row">
            <div>
              <div class="name">${this.escapeHtml(d.filename)}</div>
              <div class="sub">${this.formatSize(d.receivedSize)} · ${timeAgo}</div>
            </div>
            <span class="chip ok">Complete</span>
          </div>
        `;
      });
      html += '</div>';
    }
    
    if (active.length === 0 && history.length === 0) {
      html += '<div class="group"><div class="row"><div class="name">No downloads yet</div></div></div>';
    }
    
    html += '</div>';
    
    return html;
  }

  formatTimeAgo(timestamp) {
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
}

// Export
window.DownloadManager = DownloadManager;
window.downloadManager = new DownloadManager();
