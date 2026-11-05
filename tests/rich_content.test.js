const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');

const source = fs.readFileSync(
  path.join(__dirname, '..', 'app', 'static', 'rich-content.js'), 'utf8');

const normalize = (value) => JSON.parse(JSON.stringify(value));
const KATEX = '/static/vendor/katex/0.19.0';
const MERMAID = '/static/vendor/mermaid/12.2.0/mermaid.min.js';

function element(tagName, props = {}) {
  const classes = new Set((props.className || '').split(' ').filter(Boolean));
  return {
    tagName, dataset: {}, attributes: {}, listeners: {}, replaced: null,
    textContent: '', innerHTML: '', className: '',
    ...props,
    classList: { contains: (name) => classes.has(name) },
    setAttribute(name, value) { this.attributes[name] = value; },
    addEventListener(name, listener) { this.listeners[name] = listener; },
    replaceWith(other) { this.replaced = other; other.replacedFor = this; },
  };
}

function createHarness({ math = [], mermaidBlocks = [], theme = 'light',
                         mermaidFails = false } = {}) {
  const created = [];
  const head = { children: [], append(node) { this.children.push(node); } };
  const observers = [];
  const katexCalls = [];
  const mermaidCalls = { initialize: [], render: [] };
  const readyCallbacks = [];

  const blocks = mermaidBlocks.map((text, index) => {
    const pre = element('pre');
    const code = element('code', { textContent: text, parentElement: pre,
                                   className: 'language-mermaid' });
    pre.code = code;
    return code;
  });

  const context = {
    window: {},
    MutationObserver: class {
      constructor(callback) { this.callback = callback; observers.push(this); }
      observe(target, options) { this.target = target; this.options = options; }
    },
    document: {
      readyState: 'loading',
      currentScript: { dataset: { katexBase: KATEX, mermaidSrc: MERMAID } },
      documentElement: { dataset: { theme } },
      head,
      addEventListener(name, listener) {
        assert.equal(name, 'DOMContentLoaded');
        readyCallbacks.push(listener);
      },
      createElement(tagName) {
        const node = element(tagName);
        created.push(node);
        return node;
      },
      querySelectorAll(selector) {
        if (selector === '.math') return math;
        if (selector === 'pre > code.language-mermaid') return blocks;
        if (selector === '.mermaid-diagram') {
          return blocks.map((code) => code.parentElement.replaced).filter(Boolean);
        }
        throw new Error(`unexpected selector ${selector}`);
      },
    },
  };
  context.window = context;

  vm.runInNewContext(source, context);
  return {
    context, head, blocks, created, observers, katexCalls, mermaidCalls,
    scripts: () => head.children.filter((n) => n.tagName === 'script'),
    links: () => head.children.filter((n) => n.tagName === 'link'),
    ready() { readyCallbacks.shift()(); },
    installKatex() {
      context.katex = { render: (tex, node, options) => katexCalls.push({ tex, node, options }) };
    },
    installMermaid() {
      context.mermaid = {
        initialize: (options) => mermaidCalls.initialize.push(options),
        render: async (id, text) => {
          mermaidCalls.render.push({ id, text });
          if (mermaidFails) throw new Error('syntax error');
          return { svg: `<svg data-source="${text}"></svg>` };
        },
      };
    },
    async settle() { for (let i = 0; i < 20; i += 1) await Promise.resolve(); },
  };
}

test('a page without formulas or diagrams loads nothing', () => {
  const harness = createHarness();
  harness.ready();
  assert.equal(harness.head.children.length, 0);
  assert.equal(harness.observers.length, 0);
});

test('formulas load KaTeX once and render inline and display math', async () => {
  const inline = element('span', { className: 'math math-inline', textContent: 'a_1' });
  const block = element('p', { className: 'math math-block', textContent: '\\frac{a}{b}' });
  const harness = createHarness({ math: [inline, block] });
  harness.ready();

  assert.equal(harness.links().length, 1);
  assert.equal(harness.links()[0].href, `${KATEX}/katex.min.css`);
  assert.equal(harness.links()[0].rel, 'stylesheet');
  assert.equal(harness.scripts().length, 1);
  assert.equal(harness.scripts()[0].src, `${KATEX}/katex.min.js`);
  assert.equal(harness.katexCalls.length, 0);

  harness.installKatex();
  harness.scripts()[0].listeners.load();
  await harness.settle();

  assert.deepEqual(normalize(harness.katexCalls.map((c) => [c.tex, c.options.displayMode, c.options.throwOnError])), [
    ['a_1', false, false],
    ['\\frac{a}{b}', true, false],
  ]);
  assert.equal(inline.dataset.rendered, 'true');
});

test('formulas that fail to load stay as readable source', async () => {
  const inline = element('span', { className: 'math math-inline', textContent: 'x^2' });
  const harness = createHarness({ math: [inline] });
  harness.ready();
  harness.scripts()[0].listeners.error();
  await harness.settle();
  assert.equal(inline.textContent, 'x^2');
  assert.equal(inline.dataset.rendered, undefined);
});

test('mermaid blocks load mermaid strictly and become diagrams', async () => {
  const harness = createHarness({ mermaidBlocks: ['graph TD\nA-->B'] });
  harness.ready();
  assert.equal(harness.scripts()[0].src, MERMAID);

  harness.installMermaid();
  harness.scripts()[0].listeners.load();
  await harness.settle();

  assert.deepEqual(normalize(harness.mermaidCalls.initialize[0]), {
    startOnLoad: false, securityLevel: 'strict', theme: 'neutral' });
  assert.equal(harness.mermaidCalls.render[0].text, 'graph TD\nA-->B');
  const pre = harness.blocks[0].parentElement;
  const diagram = pre.replaced;
  assert.equal(diagram.className, 'mermaid-diagram');
  assert.equal(diagram.dataset.source, 'graph TD\nA-->B');
  assert.match(diagram.innerHTML, /^<svg/);
});

test('dark pages get the dark mermaid theme', async () => {
  const harness = createHarness({ mermaidBlocks: ['graph TD\nA-->B'], theme: 'dark' });
  harness.ready();
  harness.installMermaid();
  harness.scripts()[0].listeners.load();
  await harness.settle();
  assert.equal(harness.mermaidCalls.initialize[0].theme, 'dark');
});

test('a diagram with a syntax error keeps the original code block', async () => {
  const harness = createHarness({ mermaidBlocks: ['not a diagram'], mermaidFails: true });
  harness.ready();
  harness.installMermaid();
  harness.scripts()[0].listeners.load();
  await harness.settle();

  const pre = harness.blocks[0].parentElement;
  const diagram = pre.replaced;
  assert.equal(diagram.replaced, pre);           // the container was swapped back out
  assert.equal(pre.dataset.mermaidError, 'true');
});

test('switching the theme re-renders the diagrams', async () => {
  const harness = createHarness({ mermaidBlocks: ['graph TD\nA-->B'] });
  harness.ready();
  harness.installMermaid();
  harness.scripts()[0].listeners.load();
  await harness.settle();
  assert.equal(harness.observers.length, 1);
  assert.deepEqual(normalize(harness.observers[0].options.attributeFilter), ['data-theme']);

  harness.context.document.documentElement.dataset.theme = 'dark';
  harness.observers[0].callback();
  await harness.settle();

  assert.equal(harness.mermaidCalls.initialize.at(-1).theme, 'dark');
  assert.equal(harness.mermaidCalls.render.length, 2);
});

test('a page with both formulas and diagrams loads both libraries', () => {
  const inline = element('span', { className: 'math math-inline', textContent: 'x' });
  const harness = createHarness({ math: [inline], mermaidBlocks: ['graph TD\nA-->B'] });
  harness.ready();
  assert.deepEqual(harness.scripts().map((s) => s.src), [`${KATEX}/katex.min.js`, MERMAID]);
});
