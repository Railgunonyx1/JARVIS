/**
 * JARVIS Orbit — Parallel Agent System
 * 
 * Architecture:
 *   User Input ──┬──> Needle (fast, local, tool calls)
 *                └──> Main Model (slow, cloud, reasoning)
 * 
 * Needle processes tool calls in <50ms while the main model thinks.
 * If Needle has high confidence, it executes immediately.
 * If Needle has low confidence, it waits for the main model.
 * Both results are merged for the best response.
 */

(function() {
  'use strict';

  // ── Confidence Thresholds ──────────────────────────────────────
  var NEEDLE_HIGH_CONFIDENCE = 0.8;  // Execute immediately
  var NEEDLE_LOW_CONFIDENCE = 0.4;   // Wait for main model
  
  // ── Agent State ────────────────────────────────────────────────
  var _state = {
    mode: 'idle',           // 'idle' | 'processing' | 'done'
    needleReady: true,
    mainModelReady: false,
    currentTask: null,
    results: { needle: null, main: null },
  };

  // ── Tool Definitions ───────────────────────────────────────────
  var TOOLS = [
    { name: 'navigate', desc: 'Navigate to a URL or website', params: ['url'], confidence: 0.95 },
    { name: 'search', desc: 'Search the web for information', params: ['query'], confidence: 0.9 },
    { name: 'click', desc: 'Click an element on the page', params: ['selector'], confidence: 0.85 },
    { name: 'type_text', desc: 'Type text into an input field', params: ['selector', 'text'], confidence: 0.85 },
    { name: 'read_page', desc: 'Read the current page content', params: [], confidence: 0.95 },
    { name: 'scroll', desc: 'Scroll the page up or down', params: ['direction'], confidence: 0.95 },
    { name: 'back', desc: 'Go back to previous page', params: [], confidence: 0.95 },
    { name: 'forward', desc: 'Go forward in history', params: [], confidence: 0.95 },
    { name: 'reload', desc: 'Reload the current page', params: [], confidence: 0.95 },
    { name: 'new_tab', desc: 'Open a new tab', params: ['url'], confidence: 0.9 },
    { name: 'close_tab', desc: 'Close the current tab', params: [], confidence: 0.9 },
    { name: 'bookmark', desc: 'Bookmark the current page', params: [], confidence: 0.9 },
    { name: 'screenshot', desc: 'Take a screenshot', params: [], confidence: 0.9 },
    { name: 'summarize', desc: 'Summarize the current page', params: [], confidence: 0.85 },
    { name: 'translate', desc: 'Translate text or page', params: ['text', 'language'], confidence: 0.8 },
    { name: 'done', desc: 'Task is complete, return answer', params: ['answer'], confidence: 1.0 },
  ];

  // ── Needle Tool Router (Fast, <50ms) ──────────────────────────
  function needleRoute(query) {
    var q = query.toLowerCase().trim();
    var confidence = 0;
    var tool = null;
    var args = {};

    // Navigation (highest priority - most common)
    if (q.match(/^(navigate|go to|open|visit|load)\s+/i)) {
      var url = query.replace(/^(navigate|go to|open|visit|load)\s+/i, '').trim();
      if (!url.match(/^https?:\/\//i)) url = 'https://' + url;
      return { tool: 'navigate', args: { url: url }, confidence: 0.95 };
    }

    // Direct URL
    if (q.match(/^(https?:\/\/|www\.)/i) || q.match(/^[\w-]+\.(com|org|net|io|dev|app)/i)) {
      var url = q;
      if (!url.match(/^https?:\/\//i)) url = 'https://' + url;
      return { tool: 'navigate', args: { url: url }, confidence: 0.95 };
    }

    // Search
    if (q.match(/^(search|google|look up|find|what is|what are|who is|how to|how do|tell me about)/i)) {
      var searchQuery = q.replace(/^(search|google|look up|find|what is|what are|who is|how to|how do|tell me about)\s*(for|about|on)?\s*/i, '').trim();
      if (!searchQuery) searchQuery = query;
      return { tool: 'search', args: { query: searchQuery }, confidence: 0.9 };
    }

    // Click
    if (q.match(/^(click|press|tap|hit|select)\s+/i)) {
      var target = query.replace(/^(click|press|tap|hit|select)\s+/i, '').trim();
      return { tool: 'click', args: { selector: target || 'body' }, confidence: 0.85 };
    }

    // Type
    if (q.match(/^(type|enter|write|input|fill)\s+/i)) {
      var match = query.match(/^(type|enter|write|input|fill)\s+["'](.+?)["']/i);
      if (match) {
        return { tool: 'type_text', args: { selector: 'input:focus, input[type="text"], textarea', text: match[2] }, confidence: 0.85 };
      }
      var parts = query.replace(/^(type|enter|write|input|fill)\s+/i, '').split(' in ');
      if (parts.length === 2) {
        return { tool: 'type_text', args: { selector: parts[1].trim(), text: parts[0].trim() }, confidence: 0.85 };
      }
      return { tool: 'type_text', args: { selector: 'input', text: query.replace(/^(type|enter|write|input|fill)\s+/i, '') }, confidence: 0.8 };
    }

    // Read
    if (q.match(/^(read|get|extract|scrape|what does|what's on|what is on)/i)) {
      return { tool: 'read_page', args: {}, confidence: 0.95 };
    }

    // Scroll
    if (q.match(/scroll\s+down/i)) return { tool: 'scroll', args: { direction: 'down' }, confidence: 0.95 };
    if (q.match(/scroll\s+up/i)) return { tool: 'scroll', args: { direction: 'up' }, confidence: 0.95 };
    if (q.match(/^(go )?to (the )?bottom/i)) return { tool: 'scroll', args: { direction: 'down' }, confidence: 0.9 };
    if (q.match(/^(go )?to (the )?top/i)) return { tool: 'scroll', args: { direction: 'up' }, confidence: 0.9 };

    // Navigation buttons
    if (q.match(/^(go )?back/i)) return { tool: 'back', args: {}, confidence: 0.95 };
    if (q.match(/^(go )?forward/i)) return { tool: 'forward', args: {}, confidence: 0.95 };
    if (q.match(/^(reload|refresh)/i)) return { tool: 'reload', args: {}, confidence: 0.95 };

    // Tab management
    if (q.match(/^(open |new )?(tab|page)/i)) {
      var url = q.replace(/^(open |new )?(tab|page)\s*/i, '').trim();
      return { tool: 'new_tab', args: { url: url || 'orbit://newtab' }, confidence: 0.9 };
    }
    if (q.match(/^(close|kill) (tab|page)/i)) return { tool: 'close_tab', args: {}, confidence: 0.9 };

    // Bookmark
    if (q.match(/^(save|bookmark|add to bookmarks)/i)) return { tool: 'bookmark', args: {}, confidence: 0.9 };

    // Screenshot
    if (q.match(/^(screenshot|capture|take a (screenshot|picture|photo))/i)) return { tool: 'screenshot', args: {}, confidence: 0.9 };

    // Summarize
    if (q.match(/^(summarize|summary|tldr|tl;dr|what is this (page|about))/i)) return { tool: 'summarize', args: {}, confidence: 0.85 };

    // Done
    if (q.match(/^(done|finished|complete|stop|that's all|thanks|thank you)/i)) {
      return { tool: 'done', args: { answer: 'Task completed.' }, confidence: 1.0 };
    }

    // Default: search for the query
    return { tool: 'search', args: { query: query }, confidence: 0.7 };
  }

  // ── Tool Executor ──────────────────────────────────────────────
  function executeTool(toolCall) {
    var tool = toolCall.tool;
    var args = toolCall.args || {};

    switch (tool) {
      case 'navigate':
        window.location.href = args.url;
        return Promise.resolve({ success: true, result: 'Navigating to ' + args.url });

      case 'search':
        var searchUrl = 'https://www.google.com/search?q=' + encodeURIComponent(args.query);
        window.location.href = searchUrl;
        return Promise.resolve({ success: true, result: 'Searching: ' + args.query });

      case 'click':
        var el = document.querySelector(args.selector);
        if (el) {
          el.scrollIntoView({ behavior: 'smooth', block: 'center' });
          el.click();
          return Promise.resolve({ success: true, result: 'Clicked: ' + args.selector });
        }
        return Promise.resolve({ success: false, result: 'Not found: ' + args.selector });

      case 'type_text':
        var input = document.querySelector(args.selector);
        if (input) {
          input.focus();
          input.value = args.text;
          input.dispatchEvent(new Event('input', { bubbles: true }));
          input.dispatchEvent(new Event('change', { bubbles: true }));
          return Promise.resolve({ success: true, result: 'Typed: ' + args.text });
        }
        return Promise.resolve({ success: false, result: 'Input not found: ' + args.selector });

      case 'read_page':
        var content = document.body.innerText.substring(0, 5000);
        return Promise.resolve({ success: true, result: content });

      case 'scroll':
        window.scrollBy(0, args.direction === 'down' ? 500 : -500);
        return Promise.resolve({ success: true, result: 'Scrolled ' + args.direction });

      case 'back':
        window.history.back();
        return Promise.resolve({ success: true, result: 'Going back' });

      case 'forward':
        window.history.forward();
        return Promise.resolve({ success: true, result: 'Going forward' });

      case 'reload':
        window.location.reload();
        return Promise.resolve({ success: true, result: 'Reloading page' });

      case 'new_tab':
        var url = args.url || 'orbit://newtab';
        if (typeof createTab === 'function') createTab(url);
        return Promise.resolve({ success: true, result: 'Opened new tab' });

      case 'close_tab':
        if (typeof closeTab === 'function' && typeof activeTabId !== 'undefined') closeTab(activeTabId);
        return Promise.resolve({ success: true, result: 'Closed tab' });

      case 'bookmark':
        if (typeof addBookmark === 'function') addBookmark();
        return Promise.resolve({ success: true, result: 'Bookmarked page' });

      case 'screenshot':
        if (typeof takeScreenshot === 'function') takeScreenshot();
        return Promise.resolve({ success: true, result: 'Screenshot taken' });

      case 'summarize':
        return Promise.resolve({ success: true, result: 'Page content: ' + document.body.innerText.substring(0, 2000) });

      case 'done':
        return Promise.resolve({ success: true, done: true, result: args.answer });

      default:
        return Promise.resolve({ success: false, result: 'Unknown tool: ' + tool });
    }
  }

  // ── Parallel Agent Runner ──────────────────────────────────────
  function parallelProcess(query) {
    return new Promise(function(resolve) {
      _state.mode = 'processing';
      _state.currentTask = query;
      _state.results = { needle: null, main: null };

      // Needle runs immediately (fast path)
      var needleResult = needleRoute(query);
      _state.results.needle = needleResult;

      // If high confidence, execute immediately
      if (needleResult.confidence >= NEEDLE_HIGH_CONFIDENCE) {
        _state.mode = 'done';
        executeTool(needleResult).then(function(result) {
          resolve({
            source: 'needle',
            confidence: needleResult.confidence,
            tool: needleResult.tool,
            result: result,
            fast: true,
          });
        });
        return;
      }

      // Low confidence: wait for main model OR timeout
      var timeout = setTimeout(function() {
        if (_state.mode === 'processing') {
          _state.mode = 'done';
          executeTool(needleResult).then(function(result) {
            resolve({
              source: 'needle-timeout',
              confidence: needleResult.confidence,
              tool: needleResult.tool,
              result: result,
              fast: false,
            });
          });
        }
      }, 5000); // 5 second timeout for main model

      // Main model callback (when it responds)
      window._mainModelCallback = function(mainResult) {
        clearTimeout(timeout);
        if (_state.mode === 'processing') {
          _state.mode = 'done';
          _state.results.main = mainResult;
          resolve({
            source: 'main',
            confidence: 1.0,
            tool: mainResult.tool || 'response',
            result: mainResult,
            fast: false,
          });
        }
      };
    });
  }

  // ── Public API ──────────────────────────────────────────────────
  window.needleAgent = {
    route: needleRoute,
    execute: executeTool,
    process: parallelProcess,
    TOOLS: TOOLS,
    state: function() { return _state; },
    isReady: function() { return _state.needleReady; },
    setMainModelReady: function(ready) { _state.mainModelReady = ready; },
  };

})();
