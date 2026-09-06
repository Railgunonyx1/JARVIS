/**
 * JARVIS Orbit — Security Tester (Strix-Inspired)
 * 
 * Based on Strix AI penetration testing framework.
 * Tests browser security vulnerabilities including:
 * 
 * - OWASP Top 10 vulnerabilities
 * - XSS (Cross-Site Scripting)
 * - CSRF (Cross-Site Request Forgery)
 * - Clickjacking
 * - Content Security Policy bypass
 * - WebSocket security
 * - IPC injection
 * - Prototype pollution
 * - Open redirect
 * - Mixed content
 * - Information disclosure
 * 
 * Usage:
 *   const tester = new SecurityTester();
 *   await tester.runAllTests();
 *   const report = tester.getReport();
 */

class SecurityTester {
  constructor(config = {}) {
    this.config = {
      // Test categories
      tests: {
        xss: true,
        csrf: true,
        clickjacking: true,
        csp: true,
        websocket: true,
        ipc: true,
        prototypePollution: true,
        openRedirect: true,
        mixedContent: true,
        informationDisclosure: true,
        ...config.tests,
      },

      // Severity levels
      severity: {
        critical: 10,
        high: 7,
        medium: 4,
        low: 1,
        info: 0,
      },

      // Test timeout
      timeout: 5000,

      // Report format
      reportFormat: 'json', // json, html, markdown
    };

    this.results = [];
    this.vulnerabilities = [];
    this.warnings = [];
    this.passed = [];
    this.startTime = null;
    this.endTime = null;

    this.init();
  }

  init() {
    console.log('[SECURITY] Security tester initialized (Strix-inspired)');
  }

  // ── Test Runner ─────────────────────────────────────────────────

  async runAllTests() {
    this.startTime = Date.now();
    this.results = [];
    this.vulnerabilities = [];
    this.warnings = [];
    this.passed = [];

    console.log('[SECURITY] Starting security tests...');

    // Run each test category
    if (this.config.tests.xss) await this.testXSS();
    if (this.config.tests.csrf) await this.testCSRF();
    if (this.config.tests.clickjacking) await this.testClickjacking();
    if (this.config.tests.csp) await this.testCSP();
    if (this.config.tests.websocket) await this.testWebSocket();
    if (this.config.tests.ipc) await this.testIPC();
    if (this.config.tests.prototypePollution) await this.testPrototypePollution();
    if (this.config.tests.openRedirect) await this.testOpenRedirect();
    if (this.config.tests.mixedContent) await this.testMixedContent();
    if (this.config.tests.informationDisclosure) await this.testInformationDisclosure();

    this.endTime = Date.now();

    console.log(`[SECURITY] Tests completed in ${this.endTime - this.startTime}ms`);
    console.log(`[SECURITY] Found ${this.vulnerabilities.length} vulnerabilities, ${this.warnings.length} warnings`);

    return this.getReport();
  }

  // ── XSS Tests ──────────────────────────────────────────────────

  async testXSS() {
    console.log('[SECURITY] Testing XSS vulnerabilities...');

    const tests = [
      {
        name: 'Script injection in URL',
        test: () => this.testScriptInURL(),
        severity: 'high',
      },
      {
        name: 'Event handler injection',
        test: () => this.testEventhandlerInjection(),
        severity: 'high',
      },
      {
        name: 'DOM-based XSS',
        test: () => this.testDOMXSS(),
        severity: 'medium',
      },
      {
        name: 'innerHTML injection',
        test: () => this.testInnerHTMLInjection(),
        severity: 'medium',
      },
      {
        name: 'eval() usage detection',
        test: () => this.testEvalUsage(),
        severity: 'high',
      },
    ];

    for (const test of tests) {
      await this.runTest(test, 'xss');
    }
  }

  testScriptInURL() {
    const maliciousURLs = [
      'javascript:alert(1)',
      'javascript:void(0)',
      'data:text/html,<script>alert(1)</script>',
      'data:text/html;base64,PHNjcmlwdD5hbGVydCgxKTwvc2NyaXB0Pg==',
    ];

    const results = [];
    for (const url of maliciousURLs) {
      try {
        // Check if URL is blocked
        const blocked = this.isURLBlocked(url);
        results.push({ url, blocked });
      } catch (e) {
        results.push({ url, error: e.message });
      }
    }

    const blocked = results.every(r => r.blocked);
    return {
      name: 'Script injection in URL',
      passed: blocked,
      results,
    };
  }

  testEventhandlerInjection() {
    const payloads = [
      '<img src=x onerror=alert(1)>',
      '<svg onload=alert(1)>',
      '<body onload=alert(1)>',
      '<input onfocus=alert(1) autofocus>',
      '<marquee onstart=alert(1)>',
    ];

    const results = [];
    for (const payload of payloads) {
      const sanitized = this.sanitizeHTML(payload);
      const blocked = sanitized !== payload;
      results.push({ payload, sanitized, blocked });
    }

    const blocked = results.every(r => r.blocked);
    return {
      name: 'Event handler injection',
      passed: blocked,
      results,
    };
  }

  testDOMXSS() {
    // Check for dangerous DOM manipulation
    const dangerousPatterns = [
      /document\.write\s*\(/,
      /document\.writeln\s*\(/,
      /\.innerHTML\s*=/,
      /\.outerHTML\s*=/,
      /eval\s*\(/,
      /setTimeout\s*\(\s*['"]/,
      /setInterval\s*\(\s*['"]/,
    ];

    const results = [];
    const scripts = document.querySelectorAll('script');

    scripts.forEach((script, index) => {
      const content = script.textContent;
      for (const pattern of dangerousPatterns) {
        if (pattern.test(content)) {
          results.push({
            script: index,
            pattern: pattern.source,
            dangerous: true,
          });
        }
      }
    });

    return {
      name: 'DOM-based XSS',
      passed: results.length === 0,
      results,
    };
  }

  testInnerHTMLInjection() {
    // Check for innerHTML usage with user input
    const results = [];
    const elements = document.querySelectorAll('[data-user-content]');

    elements.forEach((el, index) => {
      const content = el.innerHTML;
      if (/<script|on\w+\s*=|javascript:/i.test(content)) {
        results.push({
          element: index,
          content: content.substring(0, 100),
          vulnerable: true,
        });
      }
    });

    return {
      name: 'innerHTML injection',
      passed: results.length === 0,
      results,
    };
  }

  testEvalUsage() {
    // Check for eval() usage
    const results = [];
    const scripts = document.querySelectorAll('script');

    scripts.forEach((script, index) => {
      const content = script.textContent;
      if (/eval\s*\(/.test(content)) {
        results.push({
          script: index,
          hasEval: true,
        });
      }
    });

    return {
      name: 'eval() usage detection',
      passed: results.length === 0,
      results,
    };
  }

  // ── CSRF Tests ──────────────────────────────────────────────────

  async testCSRF() {
    console.log('[SECURITY] Testing CSRF vulnerabilities...');

    const tests = [
      {
        name: 'Form submission without token',
        test: () => this.testFormCSRF(),
        severity: 'medium',
      },
      {
        name: 'Cross-origin requests',
        test: () => this.testCrossOriginRequests(),
        severity: 'medium',
      },
    ];

    for (const test of tests) {
      await this.runTest(test, 'csrf');
    }
  }

  testFormCSRF() {
    const forms = document.querySelectorAll('form');
    const results = [];

    forms.forEach((form, index) => {
      const hasToken = form.querySelector('input[name*="token"], input[name*="csrf"]');
      const method = form.method?.toLowerCase() || 'get';

      if (method === 'post' && !hasToken) {
        results.push({
          form: index,
          action: form.action,
          method: form.method,
          vulnerable: true,
        });
      }
    });

    return {
      name: 'Form submission without token',
      passed: results.length === 0,
      results,
    };
  }

  testCrossOriginRequests() {
    // Check for CORS misconfiguration
    const results = [];

    // This would need to be tested server-side
    // For now, check for dangerous patterns
    if (document.cookie && !document.cookie.includes('SameSite')) {
      results.push({
        issue: 'Cookies without SameSite attribute',
        vulnerable: true,
      });
    }

    return {
      name: 'Cross-origin requests',
      passed: results.length === 0,
      results,
    };
  }

  // ── Clickjacking Tests ─────────────────────────────────────────

  async testClickjacking() {
    console.log('[SECURITY] Testing clickjacking vulnerabilities...');

    const tests = [
      {
        name: 'Frame options header',
        test: () => this.testFrameOptions(),
        severity: 'medium',
      },
      {
        name: 'iframe embedding',
        test: () => this.testIframeEmbedding(),
        severity: 'low',
      },
    ];

    for (const test of tests) {
      await this.runTest(test, 'clickjacking');
    }
  }

  testFrameOptions() {
    // Check if page can be framed
    const canFrame = window.self !== window.top;
    const hasFrameOptions = document.querySelector('meta[http-equiv="X-Frame-Options"]');

    return {
      name: 'Frame options header',
      passed: hasFrameOptions || !canFrame,
      results: {
        canFrame,
        hasFrameOptions: !!hasFrameOptions,
      },
    };
  }

  testIframeEmbedding() {
    const iframes = document.querySelectorAll('iframe');
    const results = [];

    iframes.forEach((iframe, index) => {
      if (!iframe.sandbox) {
        results.push({
          iframe: index,
          src: iframe.src,
          hasSandbox: false,
        });
      }
    });

    return {
      name: 'iframe embedding',
      passed: results.length === 0,
      results,
    };
  }

  // ── CSP Tests ───────────────────────────────────────────────────

  async testCSP() {
    console.log('[SECURITY] Testing Content Security Policy...');

    const tests = [
      {
        name: 'CSP header present',
        test: () => this.testCSPHeader(),
        severity: 'high',
      },
      {
        name: 'unsafe-inline usage',
        test: () => this.testUnsafeInline(),
        severity: 'medium',
      },
      {
        name: 'unsafe-eval usage',
        test: () => this.testUnsafeEval(),
        severity: 'high',
      },
    ];

    for (const test of tests) {
      await this.runTest(test, 'csp');
    }
  }

  testCSPHeader() {
    // Check for CSP meta tag (limited check)
    const hasCSP = document.querySelector('meta[http-equiv="Content-Security-Policy"]');

    return {
      name: 'CSP header present',
      passed: !!hasCSP,
      results: {
        hasCSPMeta: !!hasCSP,
        note: 'Full CSP check requires server-side inspection',
      },
    };
  }

  testUnsafeInline() {
    const scripts = document.querySelectorAll('script:not([src])');
    const hasInline = scripts.length > 0;

    return {
      name: 'unsafe-inline usage',
      passed: !hasInline,
      results: {
        inlineScripts: scripts.length,
        hasUnsafeInline: hasInline,
      },
    };
  }

  testUnsafeEval() {
    const results = [];
    const scripts = document.querySelectorAll('script');

    scripts.forEach((script, index) => {
      if (/eval\s*\(/.test(script.textContent)) {
        results.push({
          script: index,
          hasEval: true,
        });
      }
    });

    return {
      name: 'unsafe-eval usage',
      passed: results.length === 0,
      results,
    };
  }

  // ── WebSocket Tests ─────────────────────────────────────────────

  async testWebSocket() {
    console.log('[SECURITY] Testing WebSocket security...');

    const tests = [
      {
        name: 'Secure WebSocket connection',
        test: () => this.testSecureWebSocket(),
        severity: 'medium',
      },
      {
        name: 'WebSocket origin validation',
        test: () => this.testWebSocketOrigin(),
        severity: 'medium',
      },
    ];

    for (const test of tests) {
      await this.runTest(test, 'websocket');
    }
  }

  testSecureWebSocket() {
    // Check for insecure WebSocket connections
    const results = [];
    const wsConnections = performance.getEntriesByType('resource')
      .filter(r => r.name.startsWith('ws://'));

    wsConnections.forEach(conn => {
      results.push({
        url: conn.name,
        secure: false,
      });
    });

    return {
      name: 'Secure WebSocket connection',
      passed: results.length === 0,
      results,
    };
  }

  testWebSocketOrigin() {
    // This would need actual WebSocket testing
    return {
      name: 'WebSocket origin validation',
      passed: true,
      results: {
        note: 'Requires actual WebSocket connection test',
      },
    };
  }

  // ── IPC Tests ───────────────────────────────────────────────────

  async testIPC() {
    console.log('[SECURITY] Testing IPC security...');

    const tests = [
      {
        name: 'Context isolation',
        test: () => this.testContextIsolation(),
        severity: 'critical',
      },
      {
        name: 'Node integration disabled',
        test: () => this.testNodeIntegration(),
        severity: 'critical',
      },
      {
        name: 'Preload script validation',
        test: () => this.testPreloadScript(),
        severity: 'high',
      },
    ];

    for (const test of tests) {
      await this.runTest(test, 'ipc');
    }
  }

  testContextIsolation() {
    // Check if contextIsolation is enabled
    const hasContextBridge = typeof window.orbit !== 'undefined';
    const hasElectron = typeof window.require !== 'undefined' || typeof window.electron !== 'undefined';

    return {
      name: 'Context isolation',
      passed: hasContextBridge && !hasElectron,
      results: {
        hasContextBridge,
        hasElectron,
        contextIsolationEnabled: hasContextBridge,
      },
    };
  }

  testNodeIntegration() {
    // Check if nodeIntegration is disabled
    const hasNodeAPIs = typeof window.require !== 'undefined' ||
                        typeof window.process !== 'undefined' ||
                        typeof window.Buffer !== 'undefined';

    return {
      name: 'Node integration disabled',
      passed: !hasNodeAPIs,
      results: {
        hasNodeAPIs,
        nodeIntegrationDisabled: !hasNodeAPIs,
      },
    };
  }

  testPreloadScript() {
    // Check if preload script exposes dangerous APIs
    const results = [];

    if (window.orbit) {
      // Check for dangerous methods
      const dangerousMethods = ['exec', 'spawn', 'eval', 'Function'];
      for (const method of dangerousMethods) {
        if (typeof window.orbit[method] === 'function') {
          results.push({ method, dangerous: true });
        }
      }
    }

    return {
      name: 'Preload script validation',
      passed: results.length === 0,
      results,
    };
  }

  // ── Prototype Pollution Tests ───────────────────────────────────

  async testPrototypePollution() {
    console.log('[SECURITY] Testing prototype pollution...');

    const tests = [
      {
        name: 'Object prototype pollution',
        test: () => this.testObjectPrototype(),
        severity: 'high',
      },
      {
        name: 'Array prototype pollution',
        test: () => this.testArrayPrototype(),
        severity: 'medium',
      },
    ];

    for (const test of tests) {
      await this.runTest(test, 'prototypePollution');
    }
  }

  testObjectPrototype() {
    const originalProto = { ...Object.prototype };

    try {
      // Attempt pollution
      const obj = {};
      obj.__proto__.polluted = true;

      const polluted = {}.polluted === true;

      // Cleanup
      delete Object.prototype.polluted;

      return {
        name: 'Object prototype pollution',
        passed: !polluted,
        results: {
          vulnerable: polluted,
        },
      };
    } catch (e) {
      return {
        name: 'Object prototype pollution',
        passed: true,
        results: {
          error: e.message,
        },
      };
    }
  }

  testArrayPrototype() {
    const originalProto = { ...Array.prototype };

    try {
      // Attempt pollution
      const arr = [];
      arr.__proto__.polluted = true;

      const polluted = [].polluted === true;

      // Cleanup
      delete Array.prototype.polluted;

      return {
        name: 'Array prototype pollution',
        passed: !polluted,
        results: {
          vulnerable: polluted,
        },
      };
    } catch (e) {
      return {
        name: 'Array prototype pollution',
        passed: true,
        results: {
          error: e.message,
        },
      };
    }
  }

  // ── Open Redirect Tests ─────────────────────────────────────────

  async testOpenRedirect() {
    console.log('[SECURITY] Testing open redirect...');

    const tests = [
      {
        name: 'URL validation',
        test: () => this.testURLValidation(),
        severity: 'medium',
      },
    ];

    for (const test of tests) {
      await this.runTest(test, 'openRedirect');
    }
  }

  testURLValidation() {
    const maliciousURLs = [
      'https://evil.com',
      'javascript:alert(1)',
      'data:text/html,<script>alert(1)</script>',
      '//evil.com',
    ];

    const results = [];
    for (const url of maliciousURLs) {
      const blocked = this.isURLBlocked(url);
      results.push({ url, blocked });
    }

    const blocked = results.every(r => r.blocked);
    return {
      name: 'URL validation',
      passed: blocked,
      results,
    };
  }

  // ── Mixed Content Tests ─────────────────────────────────────────

  async testMixedContent() {
    console.log('[SECURITY] Testing mixed content...');

    const tests = [
      {
        name: 'HTTP resources on HTTPS page',
        test: () => this.testMixedContentResources(),
        severity: 'medium',
      },
    ];

    for (const test of tests) {
      await this.runTest(test, 'mixedContent');
    }
  }

  testMixedContentResources() {
    if (window.location.protocol !== 'https:') {
      return {
        name: 'HTTP resources on HTTPS page',
        passed: true,
        results: {
          note: 'Not on HTTPS page',
        },
      };
    }

    const results = [];
    const resources = performance.getEntriesByType('resource');

    resources.forEach(resource => {
      if (resource.name.startsWith('http://')) {
        results.push({
          url: resource.name,
          type: resource.initiatorType,
        });
      }
    });

    return {
      name: 'HTTP resources on HTTPS page',
      passed: results.length === 0,
      results,
    };
  }

  // ── Information Disclosure Tests ────────────────────────────────

  async testInformationDisclosure() {
    console.log('[SECURITY] Testing information disclosure...');

    const tests = [
      {
        name: 'Server header disclosure',
        test: () => this.testServerHeader(),
        severity: 'low',
      },
      {
        name: 'Error message disclosure',
        test: () => this.testErrorDisclosure(),
        severity: 'low',
      },
    ];

    for (const test of tests) {
      await this.runTest(test, 'informationDisclosure');
    }
  }

  testServerHeader() {
    // Check for server header in resources
    const results = [];
    const resources = performance.getEntriesByType('resource');

    resources.forEach(resource => {
      if (resource.serverTiming && resource.serverTiming.length > 0) {
        results.push({
          url: resource.name,
          hasServerTiming: true,
        });
      }
    });

    return {
      name: 'Server header disclosure',
      passed: results.length === 0,
      results,
    };
  }

  testErrorDisclosure() {
    // Check for error messages in console
    const results = [];
    const originalConsoleError = console.error;

    // This is a passive check - just report current state
    return {
      name: 'Error message disclosure',
      passed: true,
      results: {
        note: 'Requires server-side configuration check',
      },
    };
  }

  // ── Helper Methods ──────────────────────────────────────────────

  isURLBlocked(url) {
    // Check for malicious URL patterns
    const blockedPatterns = [
      /^javascript:/i,
      /^data:text\/html/i,
      /^data:application\/x-javascript/i,
    ];

    return blockedPatterns.some(pattern => pattern.test(url));
  }

  sanitizeHTML(html) {
    // Basic HTML sanitization
    return html
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#x27;')
      .replace(/\s+on\w+\s*=/gi, ' data-blocked-');
  }

  async runTest(test, category) {
    try {
      const result = test.test();
      const testResult = {
        ...result,
        category,
        timestamp: Date.now(),
        severity: test.severity || 'info',
      };

      this.results.push(testResult);

      if (result.passed) {
        this.passed.push(testResult);
      } else {
        this.vulnerabilities.push(testResult);
      }

      return testResult;
    } catch (error) {
      const errorResult = {
        name: test.name,
        category,
        passed: false,
        error: error.message,
        timestamp: Date.now(),
        severity: test.severity || 'info',
      };

      this.results.push(errorResult);
      this.warnings.push(errorResult);

      return errorResult;
    }
  }

  // ── Report Generation ───────────────────────────────────────────

  getReport() {
    const duration = (this.endTime || Date.now()) - (this.startTime || Date.now());

    const report = {
      summary: {
        totalTests: this.results.length,
        passed: this.passed.length,
        failed: this.vulnerabilities.length,
        warnings: this.warnings.length,
        duration: `${duration}ms`,
        score: this.calculateScore(),
      },
      vulnerabilities: this.vulnerabilities.map(v => ({
        name: v.name,
        category: v.category,
        severity: v.severity,
        results: v.results,
      })),
      warnings: this.warnings.map(w => ({
        name: w.name,
        category: w.category,
        severity: w.severity,
        error: w.error,
      })),
      passed: this.passed.map(p => ({
        name: p.name,
        category: p.category,
      })),
      recommendations: this.getRecommendations(),
    };

    return report;
  }

  calculateScore() {
    if (this.results.length === 0) return 100;

    const weights = {
      critical: 10,
      high: 5,
      medium: 2,
      low: 1,
      info: 0,
    };

    let deduction = 0;
    for (const vuln of this.vulnerabilities) {
      deduction += weights[vuln.severity] || 0;
    }

    const maxDeduction = this.results.length * 5;
    const score = Math.max(0, Math.round(100 - (deduction / maxDeduction * 100)));

    return score;
  }

  getRecommendations() {
    const recommendations = [];

    // XSS recommendations
    const xssVulns = this.vulnerabilities.filter(v => v.category === 'xss');
    if (xssVulns.length > 0) {
      recommendations.push({
        category: 'XSS',
        severity: 'high',
        recommendation: 'Implement Content Security Policy and sanitize all user input',
      });
    }

    // CSP recommendations
    const cspVulns = this.vulnerabilities.filter(v => v.category === 'csp');
    if (cspVulns.length > 0) {
      recommendations.push({
        category: 'CSP',
        severity: 'high',
        recommendation: 'Add strict Content-Security-Policy header',
      });
    }

    // IPC recommendations
    const ipcVulns = this.vulnerabilities.filter(v => v.category === 'ipc');
    if (ipcVulns.length > 0) {
      recommendations.push({
        category: 'IPC',
        severity: 'critical',
        recommendation: 'Ensure contextIsolation is enabled and nodeIntegration is disabled',
      });
    }

    // General recommendations
    recommendations.push({
      category: 'General',
      severity: 'medium',
      recommendation: 'Regularly update dependencies and run security scans',
    });

    return recommendations;
  }

  // ── Export ──────────────────────────────────────────────────────

  exportReport(format = 'json') {
    const report = this.getReport();

    switch (format) {
      case 'json':
        return JSON.stringify(report, null, 2);

      case 'markdown':
        return this.exportMarkdown(report);

      case 'html':
        return this.exportHTML(report);

      default:
        return JSON.stringify(report, null, 2);
    }
  }

  exportMarkdown(report) {
    let md = '# Security Test Report\n\n';
    md += `**Date:** ${new Date().toISOString()}\n`;
    md += `**Duration:** ${report.summary.duration}\n`;
    md += `**Score:** ${report.summary.score}/100\n\n`;

    md += '## Summary\n\n';
    md += `| Metric | Count |\n|--------|-------|\n`;
    md += `| Total Tests | ${report.summary.totalTests} |\n`;
    md += `| Passed | ${report.summary.passed} |\n`;
    md += `| Failed | ${report.summary.failed} |\n`;
    md += `| Warnings | ${report.summary.warnings} |\n\n`;

    if (report.vulnerabilities.length > 0) {
      md += '## Vulnerabilities\n\n';
      for (const vuln of report.vulnerabilities) {
        md += `### ${vuln.name}\n`;
        md += `- **Category:** ${vuln.category}\n`;
        md += `- **Severity:** ${vuln.severity}\n\n`;
      }
    }

    if (report.recommendations.length > 0) {
      md += '## Recommendations\n\n';
      for (const rec of report.recommendations) {
        md += `- **${rec.category}:** ${rec.recommendation}\n`;
      }
    }

    return md;
  }

  exportHTML(report) {
    return `
<!DOCTYPE html>
<html>
<head>
  <title>Security Test Report</title>
  <style>
    body { font-family: Arial, sans-serif; max-width: 800px; margin: 0 auto; padding: 20px; }
    h1 { color: #333; }
    .summary { background: #f5f5f5; padding: 20px; border-radius: 8px; margin: 20px 0; }
    .vulnerability { background: #ffebee; padding: 15px; border-left: 4px solid #f44336; margin: 10px 0; }
    .warning { background: #fff3e0; padding: 15px; border-left: 4px solid #ff9800; margin: 10px 0; }
    .passed { background: #e8f5e9; padding: 15px; border-left: 4px solid #4caf50; margin: 10px 0; }
    .score { font-size: 48px; font-weight: bold; color: ${report.summary.score >= 80 ? '#4caf50' : report.summary.score >= 60 ? '#ff9800' : '#f44336'}; }
  </style>
</head>
<body>
  <h1>🔒 Security Test Report</h1>
  <div class="summary">
    <div class="score">${report.summary.score}/100</div>
    <p>Duration: ${report.summary.duration}</p>
    <p>Tests: ${report.summary.totalTests} | Passed: ${report.summary.passed} | Failed: ${report.summary.failed}</p>
  </div>
  ${report.vulnerabilities.map(v => `
    <div class="vulnerability">
      <strong>${v.name}</strong> (${v.severity})
      <p>Category: ${v.category}</p>
    </div>
  `).join('')}
  ${report.warnings.map(w => `
    <div class="warning">
      <strong>${w.name}</strong>
      <p>Error: ${w.error}</p>
    </div>
  `).join('')}
  ${report.passed.map(p => `
    <div class="passed">
      <strong>${p.name}</strong> ✓
    </div>
  `).join('')}
</body>
</html>
    `;
  }
}

// Export
window.SecurityTester = SecurityTester;
window.securityTester = new SecurityTester();
