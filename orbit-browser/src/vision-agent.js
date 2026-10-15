/**
 * JARVIS Orbit — Vision Agent Integration
 * 
 * Based on browser-use's multimodal approach:
 * - Captures page screenshots for vision-capable LLMs
 * - Provides page accessibility tree alongside screenshots
 * - Enables "what do you see?" queries
 * - Self-healing: retries failed actions with visual context
 */

(function() {
  'use strict';

  const VISION_API = {
    // Screenshot capture endpoint (via DSH)
    capture: '/v1/screenshot',
    // Vision analysis endpoint
    analyze: '/v1/vision/analyze',
    // Accessibility tree endpoint
    accessibility: '/v1/accessibility/tree',
  };

  const MAX_SCREENSHOT_SIZE = 1280; // Max dimension for screenshots
  const SCREENSHOT_QUALITY = 0.8;   // JPEG quality

  class VisionAgent {
    constructor(options = {}) {
      this.baseUrl = options.baseUrl || 'http://127.0.0.1:8170';
      this.sessionId = options.sessionId || 'vision-' + Date.now();
      this.lastScreenshot = null;
      this.lastAnalysis = null;
      this.history = [];
      this.maxHistory = 20;
      this._enabled = true;
    }

    /**
     * Capture a screenshot of the current page
     * @param {string} tabId - Optional tab ID to capture
     * @returns {Promise<{dataUrl: string, timestamp: number}>}
     */
    async captureScreenshot(tabId) {
      try {
        // Use Electron's webview capturePage
        const webview = this._getActiveWebview(tabId);
        if (!webview) {
          return { success: false, error: 'No active webview' };
        }

        const image = await webview.capturePage();
        const dataUrl = image.toDataURL('image/jpeg', SCREENSHOT_QUALITY);
        
        this.lastScreenshot = {
          dataUrl,
          timestamp: Date.now(),
          url: webview.getURL(),
          title: document.title,
        };

        return { success: true, ...this.lastScreenshot };
      } catch (error) {
        console.error('[VISION] Screenshot capture failed:', error);
        return { success: false, error: error.message };
      }
    }

    /**
     * Get the accessibility tree of the current page
     * @returns {Promise<{tree: object, text: string}>}
     */
    async getAccessibilityTree(tabId) {
      try {
        const webview = this._getActiveWebview(tabId);
        if (!webview) {
          return { success: false, error: 'No active webview' };
        }

        // Inject script to extract accessibility tree
        const result = await webview.executeJavaScript(`
          (function() {
            function extractTree(node, depth = 0) {
              if (depth > 5) return null;
              const role = node.getAttribute?.('role') || node.tagName?.toLowerCase() || '';
              const text = node.textContent?.trim().slice(0, 100) || '';
              const children = [];
              for (const child of node.children || []) {
                const subtree = extractTree(child, depth + 1);
                if (subtree) children.push(subtree);
              }
              return { role, text: text.slice(0, 50), children: children.slice(0, 20) };
            }
            return extractTree(document.body);
          })()
        `);

        const text = this._treeToText(result);
        return { success: true, tree: result, text };
      } catch (error) {
        console.error('[VISION] Accessibility tree extraction failed:', error);
        return { success: false, error: error.message };
      }
    }

    /**
     * Analyze the current page with vision model
     * @param {string} question - What to analyze
     * @returns {Promise<{answer: string, context: object}>}
     */
    async analyzePage(question) {
      try {
        // Capture screenshot
        const screenshot = await this.captureScreenshot();
        if (!screenshot.success) return screenshot;

        // Get accessibility tree
        const a11y = await this.getAccessibilityTree();

        // Send to vision API
        const response = await fetch(`${this.baseUrl}/v1/vision/analyze`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            sessionId: this.sessionId,
            screenshot: screenshot.dataUrl,
            question,
            accessibilityTree: a11y.text || '',
            url: screenshot.url,
            title: screenshot.title,
          }),
        });

        if (!response.ok) {
          throw new Error(`Vision API returned ${response.status}`);
        }

        const result = await response.json();
        
        // Store in history
        this.history.push({
          question,
          answer: result.answer,
          screenshot: screenshot.dataUrl,
          timestamp: Date.now(),
        });
        if (this.history.length > this.maxHistory) {
          this.history.shift();
        }

        this.lastAnalysis = result;
        return { success: true, ...result };
      } catch (error) {
        console.error('[VISION] Page analysis failed:', error);
        return { success: false, error: error.message };
      }
    }

    /**
     * Describe what's visible on the page
     * @returns {Promise<{description: string}>}
     */
    async describePage() {
      return this.analyzePage('Describe what is visible on this page. Include: main content, navigation elements, forms, buttons, and any interactive elements.');
    }

    /**
     * Find elements matching a description
     * @param {string} description - Natural language description of element
     * @returns {Promise<{elements: Array}>}
     */
    async findElements(description) {
      const result = await this.analyzePage(
        `Find all interactive elements that match: "${description}". ` +
        'For each element, provide: type, text, position (approximate x,y), and any attributes.'
      );
      
      if (!result.success) return result;
      
      // Parse elements from the answer
      const elements = this._parseElements(result.answer);
      return { success: true, elements };
    }

    /**
     * Self-healing: retry a failed action with visual context
     * @param {string} action - The action that failed
     * @param {string} error - The error message
     * @returns {Promise<{suggestion: string, retryAction: object}>}
     */
    async selfHeal(action, error) {
      return this.analyzePage(
        `I tried to ${action} but got this error: "${error}". ` +
        'Analyze the current page state and suggest how to fix this. ' +
        'Provide a specific alternative action.'
      );
    }

    /**
     * Get vision capabilities info
     */
    getCapabilities() {
      return {
        screenshot: true,
        accessibilityTree: true,
        visionAnalysis: true,
        elementFinding: true,
        selfHealing: true,
        multimodal: true,
      };
    }

    // ── Internal helpers ────────────────────────────────────────

    _getActiveWebview(tabId) {
      // Access the renderer's active webview
      if (window._orbitActiveWebview) return window._orbitActiveWebview();
      // Fallback: find visible webview
      const wv = document.querySelector('webview:not(.hidden)');
      return wv || null;
    }

    _treeToText(node, depth = 0) {
      if (!node) return '';
      const indent = '  '.repeat(depth);
      let text = '';
      if (node.text) {
        text += `${indent}[${node.role}] ${node.text}\n`;
      }
      for (const child of (node.children || [])) {
        text += this._treeToText(child, depth + 1);
      }
      return text;
    }

    _parseElements(answer) {
      // Simple heuristic parsing from LLM response
      const elements = [];
      const lines = answer.split('\n');
      for (const line of lines) {
        const match = line.match(/(button|link|input|select|textarea|clickable)[\s:]+["']?([^"'\n]+)["']?/i);
        if (match) {
          elements.push({
            type: match[1].toLowerCase(),
            text: match[2].trim(),
          });
        }
      }
      return elements;
    }
  }

  // ── Expose to window ──────────────────────────────────────────
  window.visionAgent = new VisionAgent();

  // Bridge: expose activeWebview getter for vision agent
  if (typeof window._orbitActiveWebview === 'undefined') {
    window._orbitActiveWebview = function() {
      return document.querySelector('webview:not(.hidden)');
    };
  }

  console.log('[VISION] Vision Agent loaded — multimodal capabilities available');

})();
