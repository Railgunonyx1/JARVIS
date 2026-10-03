/**
 * JARVIS Orbit — Performance Monitor
 * Real-time performance monitoring with efficiency recommendations
 */
class PerformanceMonitor {
  constructor() {
    this.metrics = {
      memory: { used: 0, limit: 0, percentage: 0 },
      cpu: { usage: 0 },
      tabs: { count: 0, sleeping: 0, memory: 0 },
      network: { requests: 0, bytes: 0 },
      rendering: { fps: 60, jank: 0 }
    };
    this.history = [];
    this.isMonitoring = false;
    this.init();
  }

  init() {
    this.startMonitoring();
    this.setupUI();
  }

  startMonitoring() {
    this.isMonitoring = true;
    this.updateMetrics();
    setInterval(() => this.updateMetrics(), 5000); // Update every 5 seconds
  }

  stopMonitoring() {
    this.isMonitoring = false;
  }

  async updateMetrics() {
    if (!this.isMonitoring) return;

    try {
      // Get memory usage
      if (performance.memory) {
        this.metrics.memory = {
          used: Math.round(performance.memory.usedJSHeapSize / 1024 / 1024),
          limit: Math.round(performance.memory.jsHeapSizeLimit / 1024 / 1024),
          percentage: Math.round((performance.memory.usedJSHeapSize / performance.memory.jsHeapSizeLimit) * 100)
        };
      }

      // Get tab count
      this.metrics.tabs.count = window.tabs?.length || 0;

      // Calculate FPS
      this.calculateFPS();

      // Store history
      this.history.push({
        timestamp: Date.now(),
        ...this.metrics
      });

      // Keep only last 60 entries (5 minutes)
      if (this.history.length > 60) this.history.shift();

      // Update UI
      this.updateUI();

      // Check for efficiency recommendations
      this.checkEfficiency();

    } catch (error) {
      console.error('Performance monitor error:', error);
    }
  }

  calculateFPS() {
    let frames = 0;
    const measure = () => {
      frames++;
      requestAnimationFrame(measure);
    };
    requestAnimationFrame(measure);
    
    setInterval(() => {
      this.metrics.rendering.fps = frames;
      frames = 0;
    }, 1000);
  }

  setupUI() {
    // Create performance badge
    this.badge = document.createElement('div');
    this.badge.className = 'performance-badge';
    this.badge.innerHTML = `
      <span class="perf-icon">⚡</span>
      <span class="perf-text">0 MB</span>
    `;
    this.badge.title = 'Performance Monitor';
    document.querySelector('.toolbar')?.appendChild(this.badge);

    // Create detailed panel
    this.panel = document.createElement('div');
    this.panel.className = 'performance-panel';
    this.panel.style.display = 'none';
    document.body.appendChild(this.panel);

    // Toggle panel on badge click
    this.badge.addEventListener('click', () => {
      this.panel.style.display = this.panel.style.display === 'none' ? 'block' : 'none';
      if (this.panel.style.display === 'block') this.updatePanel();
    });

    // Close panel when clicking outside
    document.addEventListener('click', (e) => {
      if (!this.panel.contains(e.target) && !this.badge.contains(e.target)) {
        this.panel.style.display = 'none';
      }
    });
  }

  updateUI() {
    if (this.badge) {
      const memText = this.metrics.memory.used ? `${this.metrics.memory.used} MB` : 'N/A';
      this.badge.querySelector('.perf-text').textContent = memText;
      
      // Color based on memory usage
      if (this.metrics.memory.percentage > 80) {
        this.badge.classList.add('critical');
        this.badge.classList.remove('warning');
      } else if (this.metrics.memory.percentage > 60) {
        this.badge.classList.add('warning');
        this.badge.classList.remove('critical');
      } else {
        this.badge.classList.remove('warning', 'critical');
      }
    }
  }

  updatePanel() {
    this.panel.innerHTML = `
      <div class="perf-panel-header">
        <h3>Performance Monitor</h3>
        <button class="perf-close">×</button>
      </div>
      <div class="perf-panel-content">
        <div class="perf-section">
          <h4>Memory</h4>
          <div class="perf-metric">
            <span>Used:</span>
            <span>${this.metrics.memory.used} MB</span>
          </div>
          <div class="perf-metric">
            <span>Limit:</span>
            <span>${this.metrics.memory.limit} MB</span>
          </div>
          <div class="perf-metric">
            <span>Usage:</span>
            <span>${this.metrics.memory.percentage}%</span>
          </div>
          <div class="perf-bar">
            <div class="perf-bar-fill" style="width: ${this.metrics.memory.percentage}%"></div>
          </div>
        </div>
        <div class="perf-section">
          <h4>Tabs</h4>
          <div class="perf-metric">
            <span>Total:</span>
            <span>${this.metrics.tabs.count}</span>
          </div>
          <div class="perf-metric">
            <span>Sleeping:</span>
            <span>${this.metrics.tabs.sleeping}</span>
          </div>
        </div>
        <div class="perf-section">
          <h4>Rendering</h4>
          <div class="perf-metric">
            <span>FPS:</span>
            <span>${this.metrics.rendering.fps}</span>
          </div>
        </div>
        <div class="perf-section">
          <h4>Efficiency Tips</h4>
          <ul class="perf-tips">
            ${this.getEfficiencyTips().map(tip => `<li>${tip}</li>`).join('')}
          </ul>
        </div>
      </div>
    `;

    // Close button
    this.panel.querySelector('.perf-close')?.addEventListener('click', () => {
      this.panel.style.display = 'none';
    });
  }

  checkEfficiency() {
    // Auto-sleep tabs if memory is high
    if (this.metrics.memory.percentage > 70 && window.performance) {
      window.performance.toggleEfficiencyMode(true);
    }
  }

  getEfficiencyTips() {
    const tips = [];
    if (this.metrics.memory.percentage > 70) {
      tips.push('Consider closing unused tabs to free memory');
    }
    if (this.metrics.tabs.count > 20) {
      tips.push('Many tabs open - use tab groups to organize');
    }
    if (this.metrics.rendering.fps < 30) {
      tips.push('Low FPS detected - check for heavy animations');
    }
    if (tips.length === 0) {
      tips.push('Performance is optimal');
    }
    return tips;
  }

  getMetrics() {
    return { ...this.metrics };
  }

  getHistory() {
    return [...this.history];
  }
}

document.addEventListener('DOMContentLoaded', () => { window.performanceMonitor = new PerformanceMonitor(); });
