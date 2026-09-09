/**
 * JARVIS Orbit — Needle AI Local Agent
 * 
 * Integrates Needle (14MB, 45M-parameter tool-calling model) for local
 * browser automation when JARVIS backend is offline.
 * 
 * Needle can: tool calling, structured extraction, confidence scoring.
 * Runs entirely in-browser via WASM — no server needed.
 */

// ── Needle Agent State ──────────────────────────────────────────
let _needleEngine = null;
let _needleReady = false;
let _needleLoading = false;
let _needleError = null;

// ── Browser Tools for Needle ────────────────────────────────────
const BROWSER_TOOLS = [
  {
    name: "navigate",
    description: "Navigate to a URL",
    parameters: {
      type: "object",
      properties: {
        url: { type: "string", description: "The URL to navigate to" }
      },
      required: ["url"]
    }
  },
  {
    name: "click",
    description: "Click an element on the page",
    parameters: {
      type: "object",
      properties: {
        selector: { type: "string", description: "CSS selector or element description" }
      },
      required: ["selector"]
    }
  },
  {
    name: "type",
    description: "Type text into an input field",
    parameters: {
      type: "object",
      properties: {
        selector: { type: "string", description: "CSS selector of input" },
        text: { type: "string", description: "Text to type" }
      },
      required: ["selector", "text"]
    }
  },
  {
    name: "read_page",
    description: "Read the current page content",
    parameters: {
      type: "object",
      properties: {},
      required: []
    }
  },
  {
    name: "search",
    description: "Search the web",
    parameters: {
      type: "object",
      properties: {
        query: { type: "string", description: "Search query" }
      },
      required: ["query"]
    }
  },
  {
    name: "scroll",
    description: "Scroll the page",
    parameters: {
      type: "object",
      properties: {
        direction: { type: "string", enum: ["up", "down"], description: "Scroll direction" }
      },
      required: ["direction"]
    }
  },
  {
    name: "wait",
    description: "Wait for a condition",
    parameters: {
      type: "object",
      properties: {
        seconds: { type: "number", description: "Seconds to wait" }
      },
      required: ["seconds"]
    }
  },
  {
    name: "done",
    description: "Task is complete, return final answer",
    parameters: {
      type: "object",
      properties: {
        answer: { type: "string", description: "Final answer or summary" }
      },
      required: ["answer"]
    }
  }
];

// ── Needle Engine Loader ────────────────────────────────────────
async function loadNeedleEngine() {
  if (_needleReady || _needleLoading) return _needleReady;
  _needleLoading = true;
  _needleError = null;

  try {
    // Try to load needle-rs WASM module
    // In production, this would be bundled. For now, use a CDN or local path.
    const needleModule = await import('needle-rs').catch(() => {
      console.warn('[Needle] needle-rs not available, using fallback tool router');
      return null;
    });

    if (needleModule) {
      await needleModule.default();
      
      // Load model weights (14MB)
      const modelUrl = 'https://huggingface.co/Cactus-Compute/needle2/resolve/main/needle2.cact';
      const response = await fetch(modelUrl);
      const modelBytes = new Uint8Array(await response.arrayBuffer());
      
      _needleEngine = needleModule.NeedleV2Wasm.load(modelBytes);
      _needleReady = true;
      console.log('[Needle] Engine loaded successfully');
    }
  } catch (err) {
    console.warn('[Needle] Failed to load:', err.message);
    _needleError = err.message;
  } finally {
    _needleLoading = false;
  }
  return _needleReady;
}

// ── Tool Router (fallback when Needle is unavailable) ───────────
function routeToolCall(query) {
  const q = query.toLowerCase();
  
  // Simple pattern matching as fallback
  if (q.includes('navigate') || q.includes('go to') || q.includes('open')) {
    const urlMatch = query.match(/(?:https?:\/\/)?[\w.-]+\.[\w]+(?:\/\S*)?/);
    return { name: 'navigate', arguments: { url: urlMatch ? urlMatch[0] : 'https://google.com' } };
  }
  if (q.includes('click') || q.includes('press')) {
    return { name: 'click', arguments: { selector: 'body' } };
  }
  if (q.includes('type') || q.includes('enter') || q.includes('write')) {
    const textMatch = query.match(/(?:type|enter|write)\s+["'](.+?)["']/i);
    return { name: 'type', arguments: { selector: 'input', text: textMatch ? textMatch[1] : '' } };
  }
  if (q.includes('read') || q.includes('get content')) {
    return { name: 'read_page', arguments: {} };
  }
  if (q.includes('search') || q.includes('google')) {
    const queryMatch = query.match(/(?:search|google)\s+(?:for\s+)?["']?(.+?)["']?\s*$/i);
    return { name: 'search', arguments: { query: queryMatch ? queryMatch[1] : query } };
  }
  if (q.includes('scroll down')) {
    return { name: 'scroll', arguments: { direction: 'down' } };
  }
  if (q.includes('scroll up')) {
    return { name: 'scroll', arguments: { direction: 'up' } };
  }
  if (q.includes('done') || q.includes('finished') || q.includes('complete')) {
    return { name: 'done', arguments: { answer: 'Task completed.' } };
  }
  
  // Default: navigate to search
  return { name: 'search', arguments: { query: query } };
}

// ── Needle Tool Call ────────────────────────────────────────────
async function needleToolCall(query) {
  if (_needleReady && _needleEngine) {
    try {
      const toolsJson = JSON.stringify(BROWSER_TOOLS);
      const result = _needleEngine.run_json(query, toolsJson);
      return JSON.parse(result);
    } catch (err) {
      console.error('[Needle] Tool call failed:', err);
      return routeToolCall(query);
    }
  }
  // Fallback to pattern matching
  return routeToolCall(query);
}

// ── Execute Tool Call ───────────────────────────────────────────
async function executeToolCall(toolCall) {
  const { name, arguments: args } = toolCall;
  
  switch (name) {
    case 'navigate':
      window.location.href = args.url;
      return { success: true, result: 'Navigated to ' + args.url };
    
    case 'click':
      const el = document.querySelector(args.selector);
      if (el) { el.click(); return { success: true, result: 'Clicked element' }; }
      return { success: false, result: 'Element not found: ' + args.selector };
    
    case 'type':
      const input = document.querySelector(args.selector);
      if (input) {
        input.value = args.text;
        input.dispatchEvent(new Event('input', { bubbles: true }));
        return { success: true, result: 'Typed: ' + args.text };
      }
      return { success: false, result: 'Input not found: ' + args.selector };
    
    case 'read_page':
      return { success: true, result: document.body.innerText.substring(0, 2000) };
    
    case 'search':
      return { success: true, result: 'Searching for: ' + args.query };
    
    case 'scroll':
      window.scrollBy(0, args.direction === 'down' ? 500 : -500);
      return { success: true, result: 'Scrolled ' + args.direction };
    
    case 'wait':
      await new Promise(r => setTimeout(r, (args.seconds || 1) * 1000));
      return { success: true, result: 'Waited ' + args.seconds + 's' };
    
    case 'done':
      return { success: true, done: true, result: args.answer };
    
    default:
      return { success: false, result: 'Unknown tool: ' + name };
  }
}

// ── Agent Loop ──────────────────────────────────────────────────
async function runNeedleAgent(task, maxSteps = 10) {
  const steps = [];
  let step = 0;
  
  while (step < maxSteps) {
    step++;
    const toolCall = await needleToolCall(task);
    steps.push({ step, tool: toolCall.name, args: toolCall.arguments });
    
    const result = await executeToolCall(toolCall);
    steps[steps.length - 1].result = result;
    
    if (result.done || toolCall.name === 'done') {
      return { success: true, answer: result.result, steps };
    }
    
    // Brief pause between steps
    await new Promise(r => setTimeout(r, 500));
  }
  
  return { success: false, answer: 'Max steps reached', steps };
}

// ── Public API ──────────────────────────────────────────────────
module.exports = {
  loadNeedleEngine,
  needleToolCall,
  executeToolCall,
  runNeedleAgent,
  BROWSER_TOOLS,
  isReady: () => _needleReady,
  isLoading: () => _needleLoading,
  getError: () => _needleError,
};
