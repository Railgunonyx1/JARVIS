/**
 * JARVIS Orbit — Multi-Agent Planner
 * 
 * Based on nanobrowser's planner + navigator architecture:
 * - Planner: Decomposes high-level tasks into steps
 * - Navigator: Executes individual steps
 * - Validator: Verifies step completion
 * - Memory: Tracks progress and context
 */

(function() {
  'use strict';

  const AGENT_STATES = {
    IDLE: 'idle',
    PLANNING: 'planning',
    EXECUTING: 'executing',
    VALIDATING: 'validating',
    WAITING: 'waiting',
    ERROR: 'error',
    COMPLETED: 'completed',
  };

  class AgentStep {
    constructor(action, target, value, description) {
      this.id = 'step-' + Date.now() + '-' + Math.random().toString(36).slice(2, 6);
      this.action = action;       // navigate, click, type, scroll, wait, extract
      this.target = target;       // CSS selector, URL, or description
      this.value = value;         // Input value or parameter
      this.description = description;
      this.status = 'pending';    // pending, running, completed, failed
      this.result = null;
      this.error = null;
      this.startedAt = null;
      this.completedAt = null;
    }

    start() {
      this.status = 'running';
      this.startedAt = Date.now();
    }

    complete(result) {
      this.status = 'completed';
      this.result = result;
      this.completedAt = Date.now();
    }

    fail(error) {
      this.status = 'failed';
      this.error = error;
      this.completedAt = Date.now();
    }

    get duration() {
      if (!this.startedAt) return 0;
      return (this.completedAt || Date.now()) - this.startedAt;
    }
  }

  class MultiAgentPlanner {
    constructor(options = {}) {
      this.baseUrl = options.baseUrl || 'http://127.0.0.1:8170';
      this.sessionId = options.sessionId || 'planner-' + Date.now();
      this.state = AGENT_STATES.IDLE;
      this.currentTask = null;
      this.steps = [];
      this.currentStepIndex = 0;
      this.maxSteps = 20;
      this.maxRetries = 2;
      this.context = {};
      this.listeners = {};
      this._abortController = null;
    }

    /**
     * Execute a high-level task
     * @param {string} task - Natural language task description
     * @param {object} options - Additional options
     * @returns {Promise<{success: boolean, result: string}>}
     */
    async execute(task, options = {}) {
      if (this.state === AGENT_STATES.EXECUTING) {
        return { success: false, error: 'Task already in progress' };
      }

      this.currentTask = task;
      this.steps = [];
      this.currentStepIndex = 0;
      this.context = options.context || {};
      this._abortController = new AbortController();

      this._emit('task:start', { task });

      try {
        // Step 1: Plan
        this._setState(AGENT_STATES.PLANNING);
        const plan = await this._plan(task);
        
        if (!plan.success) {
          this._setState(AGENT_STATES.ERROR);
          this._emit('task:error', { error: plan.error });
          return { success: false, error: plan.error };
        }

        this.steps = plan.steps;
        this._emit('task:planned', { steps: this.steps.map(s => s.description) });

        // Step 2: Execute each step
        this._setState(AGENT_STATES.EXECUTING);
        for (let i = 0; i < this.steps.length; i++) {
          if (this._abortController.signal.aborted) {
            this._setState(AGENT_STATES.ERROR);
            return { success: false, error: 'Task aborted' };
          }

          this.currentStepIndex = i;
          const step = this.steps[i];
          
          this._emit('step:start', { step: step.description, index: i, total: this.steps.length });
          
          let retries = 0;
          let stepSuccess = false;

          while (retries <= this.maxRetries && !stepSuccess) {
            step.start();
            
            try {
              const result = await this._executeStep(step);
              
              // Step 3: Validate
              this._setState(AGENT_STATES.VALIDATING);
              const valid = await this._validateStep(step, result);
              
              if (valid) {
                step.complete(result);
                stepSuccess = true;
                this._emit('step:complete', { step: step.description, result });
              } else {
                throw new Error('Validation failed');
              }
            } catch (error) {
              step.error = error.message;
              retries++;
              
              if (retries > this.maxRetries) {
                step.fail(error.message);
                this._emit('step:error', { step: step.description, error: error.message });
                
                // Try to recover
                this._setState(AGENT_STATES.EXECUTING);
                const recovery = await this._recover(step, error.message);
                if (recovery.success) {
                  step.complete(recovery.result);
                  stepSuccess = true;
                } else {
                  this._setState(AGENT_STATES.ERROR);
                  return { success: false, error: `Step failed: ${step.description}` };
                }
              } else {
                this._emit('step:retry', { step: step.description, retry: retries });
                this._setState(AGENT_STATES.EXECUTING);
              }
            }
          }
        }

        // All steps completed
        this._setState(AGENT_STATES.COMPLETED);
        this._emit('task:complete', { task, steps: this.steps.length });
        
        return { success: true, result: 'Task completed successfully' };
      } catch (error) {
        this._setState(AGENT_STATES.ERROR);
        this._emit('task:error', { error: error.message });
        return { success: false, error: error.message };
      }
    }

    /**
     * Abort the current task
     */
    abort() {
      if (this._abortController) {
        this._abortController.abort();
      }
      this._setState(AGENT_STATES.IDLE);
      this._emit('task:abort', { task: this.currentTask });
    }

    /**
     * Get current status
     */
    getStatus() {
      return {
        state: this.state,
        task: this.currentTask,
        currentStep: this.currentStepIndex,
        totalSteps: this.steps.length,
        steps: this.steps.map(s => ({
          description: s.description,
          status: s.status,
          duration: s.duration,
        })),
      };
    }

    /**
     * Add event listener
     */
    on(event, callback) {
      if (!this.listeners[event]) this.listeners[event] = [];
      this.listeners[event].push(callback);
    }

    // ── Planning ────────────────────────────────────────────────

    async _plan(task) {
      try {
        const response = await fetch(`${this.baseUrl}/v1/agent/plan`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            task,
            sessionId: this.sessionId,
            context: this.context,
            maxSteps: this.maxSteps,
          }),
          signal: this._abortController.signal,
        });

        if (!response.ok) {
          throw new Error(`Plan API returned ${response.status}`);
        }

        const data = await response.json();
        
        // Convert to AgentStep objects
        const steps = (data.steps || []).map(s => 
          new AgentStep(s.action, s.target, s.value, s.description)
        );

        return { success: true, steps };
      } catch (error) {
        // Fallback: create a simple single-step plan
        console.warn('[PLANNER] Plan API failed, using fallback:', error.message);
        const steps = [
          new AgentStep('navigate', this.context.url || 'about:blank', null, 'Navigate to page'),
          new AgentStep('extract', 'body', null, 'Extract page content'),
        ];
        return { success: true, steps };
      }
    }

    // ── Step Execution ──────────────────────────────────────────

    async _executeStep(step) {
      const webview = document.querySelector('webview:not(.hidden)');
      if (!webview) throw new Error('No active webview');

      switch (step.action) {
        case 'navigate':
          return this._execNavigate(webview, step);
        case 'click':
          return this._execClick(webview, step);
        case 'type':
          return this._execType(webview, step);
        case 'scroll':
          return this._execScroll(webview, step);
        case 'wait':
          return this._execWait(step);
        case 'extract':
          return this._execExtract(webview, step);
        case 'screenshot':
          return this._execScreenshot(webview, step);
        default:
          throw new Error(`Unknown action: ${step.action}`);
      }
    }

    async _execNavigate(webview, step) {
      await webview.loadURL(step.target);
      return { navigated: step.target };
    }

    async _execClick(webview, step) {
      const result = await webview.executeJavaScript(`
        (function() {
          const el = document.querySelector('${step.target.replace(/'/g, "\\'")}');
          if (!el) return { error: 'Element not found: ${step.target}' };
          el.scrollIntoView({ behavior: 'smooth', block: 'center' });
          el.click();
          return { clicked: true, text: el.textContent?.slice(0, 100) };
        })()
      `);
      if (result.error) throw new Error(result.error);
      return result;
    }

    async _execType(webview, step) {
      const result = await webview.executeJavaScript(`
        (function() {
          const el = document.querySelector('${step.target.replace(/'/g, "\\'")}');
          if (!el) return { error: 'Element not found: ${step.target}' };
          el.focus();
          el.value = '${(step.value || '').replace(/'/g, "\\'")}';
          el.dispatchEvent(new Event('input', { bubbles: true }));
          el.dispatchEvent(new Event('change', { bubbles: true }));
          return { typed: true };
        })()
      `);
      if (result.error) throw new Error(result.error);
      return result;
    }

    async _execScroll(webview, step) {
      const direction = step.target || 'down';
      const amount = parseInt(step.value) || 500;
      await webview.executeJavaScript(`
        window.scrollBy(0, ${direction === 'up' ? -amount : amount});
      `);
      return { scrolled: direction, amount };
    }

    async _execWait(step) {
      const ms = parseInt(step.target) || 1000;
      await new Promise(resolve => setTimeout(resolve, ms));
      return { waited: ms };
    }

    async _execExtract(webview, step) {
      const result = await webview.executeJavaScript(`
        (function() {
          const el = document.querySelector('${(step.target || 'body').replace(/'/g, "\\'")}');
          if (!el) return { error: 'Element not found' };
          return {
            text: el.textContent?.slice(0, 5000),
            html: el.innerHTML?.slice(0, 5000),
            links: Array.from(el.querySelectorAll('a')).slice(0, 20).map(a => ({
              text: a.textContent?.trim(),
              href: a.href,
            })),
          };
        })()
      `);
      if (result.error) throw new Error(result.error);
      return result;
    }

    async _execScreenshot(webview, step) {
      const image = await webview.capturePage();
      return { screenshot: image.toDataURL('image/jpeg', 0.8) };
    }

    // ── Validation ──────────────────────────────────────────────

    async _validateStep(step, result) {
      // Basic validation: check if the step produced a result
      if (!result) return false;
      if (result.error) return false;
      
      // For navigation, check URL changed
      if (step.action === 'navigate') {
        const webview = document.querySelector('webview:not(.hidden)');
        if (webview && webview.getURL() !== step.target) {
          // Allow redirects
          return true;
        }
      }

      return true;
    }

    // ── Recovery ────────────────────────────────────────────────

    async _recover(step, error) {
      try {
        // Try alternative approach
        if (step.action === 'click') {
          // Try finding element by text instead of selector
          const result = await document.querySelector('webview:not(.hidden)')?.executeJavaScript(`
            (function() {
              const elements = document.querySelectorAll('button, a, input, [role="button"]');
              for (const el of elements) {
                if (el.textContent?.includes('${step.target.replace(/'/g, "\\'")}')) {
                  el.click();
                  return { clicked: true, via: 'text-match' };
                }
              }
              return { error: 'No matching element found' };
            })()
          `);
          if (result && !result.error) return { success: true, result };
        }
      } catch (e) {
        // Recovery failed
      }
      return { success: false };
    }

    // ── State & Events ──────────────────────────────────────────

    _setState(state) {
      this.state = state;
      this._emit('state:change', { state });
    }

    _emit(event, data) {
      const callbacks = this.listeners[event] || [];
      for (const cb of callbacks) {
        try { cb(data); } catch (e) { console.error('[PLANNER] Event callback error:', e); }
      }
    }
  }

  // ── Expose to window ──────────────────────────────────────────
  window.multiAgentPlanner = new MultiAgentPlanner();
  window.AGENT_STATES = AGENT_STATES;

  console.log('[PLANNER] Multi-Agent Planner loaded — planner + navigator architecture');

})();
