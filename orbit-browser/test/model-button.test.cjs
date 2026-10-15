/* Regression harness for orbit-browser/src/js/model-button.js
 *
 * Zero-dependency: a hand-rolled DOM shim plus a fake fetch standing in for
 * GET /v1/models. Run with:  node orbit-browser/test/model-button.test.cjs
 *
 * What it pins down:
 *   - the menu renders one row per model the bridge reports (plus Auto)
 *   - offline providers are listed but not selectable
 *   - picking a row writes the SAME localStorage key the sidebar chip and
 *     /model command use, and repaints the button label
 *   - the button, outside click, and Escape all toggle the menu
 *   - the 'model' event from another surface repaints this button
 */

const fs = require('fs');
const path = require('path');
const vm = require('vm');

let failures = 0;
let checks = 0;

function ok(cond, label, extra) {
  checks += 1;
  if (cond) {
    console.log('  PASS  ' + label);
  } else {
    failures += 1;
    console.log('  FAIL  ' + label + (extra !== undefined ? '  -> ' + extra : ''));
  }
}

// ── Minimal DOM ────────────────────────────────────────────────────────
class ClassList {
  constructor(el) { this.el = el; this.set = new Set(); }
  add(c) { this.set.add(c); }
  remove(c) { this.set.delete(c); }
  contains(c) { return this.set.has(c); }
  toggle(c, force) {
    const want = force === undefined ? !this.set.has(c) : !!force;
    if (want) this.set.add(c); else this.set.delete(c);
    return want;
  }
}

class El {
  constructor(tag) {
    this.tagName = String(tag).toUpperCase();
    this.children = [];
    this.parentNode = null;
    this._listeners = {};
    this._class = new ClassList(this);
    this.dataset = {};
    this.attrs = {};
    this._text = '';
    this.hidden = false;
    this.disabled = false;
    this.id = '';
    this.title = '';
  }
  get classList() { return this._class; }
  set className(v) { this._class = new ClassList(this); String(v).split(/\s+/).filter(Boolean).forEach((c) => this._class.add(c)); }
  get className() { return Array.from(this._class.set).join(' '); }
  get textContent() {
    if (this.children.length === 0) return this._text;
    return this.children.map((c) => c.textContent).join('');
  }
  set textContent(v) { this._text = String(v); this.children = []; }
  appendChild(child) {
    // Real DOM splices a DocumentFragment's children instead of nesting it.
    if (child.tagName === 'FRAGMENT') {
      child.children.forEach((c) => { c.parentNode = this; this.children.push(c); });
      child.children = [];
      return child;
    }
    child.parentNode = this;
    this.children.push(child);
    return child;
  }
  setAttribute(k, v) { this.attrs[k] = String(v); if (k === 'id') this.id = String(v); if (k === 'title') this.title = String(v); }
  getAttribute(k) { return Object.prototype.hasOwnProperty.call(this.attrs, k) ? this.attrs[k] : null; }
  addEventListener(type, fn) { (this._listeners[type] = this._listeners[type] || []).push(fn); }
  dispatch(type, ev) {
    ev = ev || {};
    ev.type = type;
    ev.target = ev.target || this;
    ev.stopPropagation = ev.stopPropagation || function () {};
    (this._listeners[type] || []).forEach((fn) => fn.call(this, ev));
    return ev;
  }
  click() { return this.dispatch('click', { target: this }); }
  focus() { this.focused = true; }
  /** Selector subset used by the module: tag, .class, #id, and compounds. */
  matches(sel) {
    const parts = sel.trim().split(/(?=[#.])/);
    return parts.every((p) => {
      if (p[0] === '#') return this.id === p.slice(1);
      if (p[0] === '.') return this._class.contains(p.slice(1));
      return this.tagName === p.toUpperCase();
    });
  }
  closest(sel) {
    let n = this;
    while (n) { if (n.matches && n.matches(sel)) return n; n = n.parentNode; }
    return null;
  }
  all() {
    const out = [];
    (function walk(n) { n.children.forEach((c) => { out.push(c); walk(c); }); })(this);
    return out;
  }
  findAll(sel) { return this.all().filter((n) => n.matches(sel)); }
}

function makeDocument(ids) {
  const body = new El('body');
  ids.forEach((id) => { const e = new El('div'); e.id = id; body.appendChild(e); });
  return {
    readyState: 'complete',
    bodyElement: body,
    _byId: ids.reduce((acc, id) => { acc[id] = body.children.find((c) => c.id === id); return acc; }, {}),
    getElementById(id) { return this._byId[id] || null; },
    createElement(tag) { return new El(tag); },
    createDocumentFragment() { return new El('fragment'); },
    addEventListener(type, fn) { body.dispatch(type, fn ? { target: body, _doc: true } : undefined); body._listeners[type] = (body._listeners[type] || []).concat(fn || []); },
  };
}

// ── Harness ────────────────────────────────────────────────────────────
const SRC = path.join(__dirname, '..', 'src', 'js', 'model-button.js');
const code = fs.readFileSync(SRC, 'utf8');

const MODELS = [
  { id: 'ollama/llama3.2:1b', provider: 'ollama', model: 'llama3.2:1b', kind: 'local', available: true },
  { id: 'deepseek/deepseek-chat', provider: 'deepseek', model: 'deepseek-chat', kind: 'primary', available: true },
  { id: 'openai/gpt-4o', provider: 'openai', model: 'gpt-4o', kind: 'primary', available: false },
];

function buildEnv(opts) {
  opts = opts || {};
  const doc = makeDocument(['modelButton', 'modelName', 'modelMenu']);
  const store = {};
  const calls = [];
  const listeners = {};
  const storage = {
    getItem: (k) => (Object.prototype.hasOwnProperty.call(store, k) ? store[k] : null),
    setItem: (k, v) => { store[k] = String(v); },
    removeItem: (k) => { delete store[k]; },
  };
  const win = {
    localStorage: storage,
    dshNative: opts.noNative ? undefined : (function () {
      // Mirrors the real DSHNative: selectedModel is a localStorage-backed
      // accessor that emits 'model' on write -- it is the single source of
      // truth the sidebar chip and /model command also go through.
      const self = {
        config: { baseUrl: 'http://127.0.0.1:8170', authToken: 'tok' },
        listModels: async () => { calls.push('native'); return opts.models === undefined ? MODELS : opts.models; },
        on(evt, fn) { (listeners[evt] = listeners[evt] || []).push(fn); },
        emit(evt, payload) { (listeners[evt] || []).forEach((fn) => fn(payload)); },
      };
      Object.defineProperty(self, 'selectedModel', {
        get() { return storage.getItem('orbit-model') || null; },
        set(id) {
          if (id) storage.setItem('orbit-model', id); else storage.removeItem('orbit-model');
          self.emit('model', id || null);
        },
      });
      return self;
    }()),
    fetch: async (url) => {
      calls.push(url);
      if (opts.fetchThrows) throw new Error('offline');
      return { ok: true, json: async () => ({ ok: true, models: opts.models === undefined ? MODELS : opts.models }) };
    },
  };
  win.window = win;
  const sandbox = {
    window: win,
    document: doc,
    localStorage: win.localStorage,
    fetch: win.fetch,
    AbortSignal: { timeout: () => ({}) },
    console: console,
    setTimeout: setTimeout,
    clearTimeout: clearTimeout,
    Promise: Promise,
    Object: Object,
    Array: Array,
    String: String,
    Boolean: Boolean,
    JSON: JSON,
  };
  sandbox.globalThis = sandbox;
  vm.createContext(sandbox);
  vm.runInContext(code, sandbox, { filename: SRC });
  return { win, doc, store, calls, listeners };
}

function menuRows(doc) {
  const menu = doc.getElementById('modelMenu');
  return menu.findAll('.model-option');
}

(async function main() {
  console.log('model-button.js');

  // 1. Renders one row per model plus Auto.
  {
    const { doc, win } = buildEnv();
    await win.OrbitModelButton.refresh();
    win.OrbitModelButton.open();
    const rows = menuRows(doc);
    const labels = rows.map((r) => r.findAll('.model-option-label')[0].textContent);
    ok(rows.length === 4, 'renders Auto + one row per model', rows.length);
    ok(labels[0] === 'Auto', 'Auto is the first row', labels[0]);
    ok(labels.indexOf('deepseek-chat') > 0, 'model row uses the model name', labels.join(','));
    ok(doc.getElementById('modelMenu').hidden === false, 'menu is visible when open');
    ok(doc.getElementById('modelMenu').classList.contains('open'), 'menu has the .open class the CSS animates');
  }

  // 2. Offline providers are rendered but disabled.
  {
    const { doc, win } = buildEnv();
    await win.OrbitModelButton.refresh();
    win.OrbitModelButton.open();
    const offline = menuRows(doc).filter((r) => r.dataset.model === 'openai/gpt-4o')[0];
    ok(!!offline, 'offline provider is still listed');
    ok(offline && offline.disabled === true, 'offline provider cannot be selected', offline && offline.disabled);
  }

  // 3. Selecting a row writes the shared key and repaints the label.
  {
    const { doc, win, store } = buildEnv();
    await win.OrbitModelButton.refresh();
    win.OrbitModelButton.open();
    const row = menuRows(doc).filter((r) => r.dataset.model === 'deepseek/deepseek-chat')[0];
    row.click();
    ok(store['orbit-model'] === 'deepseek/deepseek-chat', 'writes the orbit-model key', store['orbit-model']);
    ok(doc.getElementById('modelName').textContent === 'deepseek-chat', 'button label follows the selection', doc.getElementById('modelName').textContent);
    ok(doc.getElementById('modelMenu').hidden === true, 'menu closes after choosing');
  }

  // 4. The sidebar chip / /model command repaints this button.
  {
    const { doc, win, store } = buildEnv();
    await win.OrbitModelButton.refresh();
    win.dshNative.selectedModel = 'openai/gpt-4o';   // emits 'model'
    ok(doc.getElementById('modelName').textContent === 'gpt-4o', "another surface's 'model' event repaints the label", doc.getElementById('modelName').textContent);
    ok(store['orbit-model'] === 'openai/gpt-4o', 'that surface owns the persistence');
    win.OrbitModelButton.select(null);
    ok(doc.getElementById('modelName').textContent === 'Auto', 'clearing the pin returns the label to Auto');
  }

  // 5. Button click toggles; outside click and Escape close.
  {
    const { doc, win } = buildEnv();
    await win.OrbitModelButton.refresh();
    const btn = doc.getElementById('modelButton');
    const menu = doc.getElementById('modelMenu');
    btn.click();
    ok(menu.hidden === false, 'button opens the menu');
    ok(btn.getAttribute('aria-expanded') === 'true', 'aria-expanded tracks the menu');
    doc.bodyElement.dispatch('click', { target: doc.getElementById('modelName') });
    ok(menu.hidden === true, 'outside click closes the menu');
    btn.click();
    doc.bodyElement.dispatch('keydown', { key: 'Escape' });
    ok(menu.hidden === true, 'Escape closes the menu');
    ok(doc.getElementById('modelButton').getAttribute('aria-expanded') === 'false', 'aria-expanded resets');
  }

  // 6. Offline kernel degrades to a hint, not an exception.
  {
    const { doc, win } = buildEnv({ models: [], fetchThrows: true });
    await win.OrbitModelButton.refresh();
    win.OrbitModelButton.open();
    const rows = menuRows(doc);
    ok(rows.length === 2, 'Auto + an offline hint, no crash', rows.length);
    ok(/kernel offline/i.test(rows[1].textContent), 'offline hint is shown', rows[1].textContent);
    ok(doc.getElementById('modelName').textContent === 'Auto', 'label still renders with no models');
  }

  // 7. Works without dshNative by hitting the bridge directly.
  {
    const { win, calls } = buildEnv({ noNative: true });
    await win.OrbitModelButton.refresh();
    ok(calls.some((c) => String(c).indexOf('/v1/models') > -1), 'falls back to GET /v1/models', calls.join(','));
    ok(win.OrbitModelButton.models().length === 3, 'models parsed from the direct fetch', win.OrbitModelButton.models().length);
  }

  console.log('\n' + (checks - failures) + '/' + checks + ' passed');
  process.exit(failures === 0 ? 0 : 1);
})().catch((e) => { console.error(e); process.exit(1); });