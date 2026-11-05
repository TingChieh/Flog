const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');

const source = fs.readFileSync(path.join(__dirname, '../app/static/search.js'), 'utf8');

function target(extra = {}) {
  return Object.assign({
    listeners: {},
    addEventListener(name, fn) { this.listeners[name] = fn; },
  }, extra);
}

test('Escape closes a populated search dialog and restores focus', () => {
  let focusRestored = false;
  const previous = {isConnected: true, focus() { focusRestored = true; }};
  const input = target({value: '中文搜索', focus() {}});
  const status = {};
  const results = target({replaceChildren() {}});
  const form = target();
  const closeButton = target();
  const trigger = target();
  const elements = {
    '[data-search-input]': input, '[data-search-status]': status,
    '[data-search-results]': results, '[data-search-form]': form,
    '[data-search-close]': closeButton,
  };
  const dialog = target({
    open: false,
    dataset: {empty: "Type to search posts."},
    querySelector(selector) { return elements[selector]; },
    showModal() { this.open = true; },
    close() { this.open = false; this.listeners.close(); },
  });
  const document = target({
    documentElement: {clientWidth: 1000, style: {}},
    activeElement: previous,
    querySelector(selector) { return selector === '[data-search-dialog]' ? dialog : trigger; },
  });
  vm.runInNewContext(source, {document, window: {innerWidth: 1000, getComputedStyle() { return {paddingRight: "0"}; }}, clearTimeout, setTimeout});
  trigger.listeners.click({preventDefault() {}});
  assert.equal(dialog.open, true);
  let prevented = false;
  dialog.listeners.keydown({key: 'Escape', preventDefault() { prevented = true; }});
  assert.equal(prevented, true);
  assert.equal(dialog.open, false);
  assert.equal(focusRestored, true);
  assert.equal(input.value, "");
  assert.equal(status.textContent, "Type to search posts.");
});

test('search renders highlighted segments as elements and hostile text as text', async () => {
  function element(tag) {
    return target({tag, children: [], append(...nodes) { this.children.push(...nodes); },
      replaceChildren(...nodes) { this.children = nodes; }});
  }
  const input = target({value: '中文', focus() {}}), status = {}, results = element('ul');
  const form = target(), trigger = target(), closeButton = target();
  const fields = {'[data-search-input]': input, '[data-search-status]': status,
    '[data-search-results]': results, '[data-search-form]': form, '[data-search-close]': closeButton};
  const dialog = target({dataset: {api: '/api/search'}, querySelector(s) { return fields[s]; }, showModal() {}});
  const document = target({querySelector(s) { return s === '[data-search-dialog]' ? dialog : trigger; },
    createElement: element, createTextNode(text) { return {text}; }});
  const data = {results: [{url: '/post/1', title: '中文 title', date: '2026-01-01',
    snippet: '<mark>中文</mark> &lt;img&gt;',
    title_segments: [{text: '中文', highlight: true}, {text: ' title', highlight: false}],
    snippet_segments: [{text: '中文', highlight: true}, {text: ' <img src=x onerror=alert(1)>', highlight: false}]}]};
  vm.runInNewContext(source, {document, clearTimeout() {}, setTimeout(fn) { fn(); }, AbortController,
    fetch: async () => ({ok: true, json: async () => data})});
  input.listeners.input();
  await new Promise(resolve => setImmediate(resolve));
  const [title, excerpt] = results.children[0].children[0].children;
  assert.equal(title.children[0].tag, 'mark');
  assert.equal(title.children[0].textContent, '中文');
  assert.equal(excerpt.children[0].tag, 'mark');
  assert.equal(excerpt.children[1].text, ' <img src=x onerror=alert(1)>');
  assert.equal(excerpt.textContent, undefined);
});

test('opening locks scroll without shifting content and closing restores styles', () => {
  const input = target({focus() {}, value: ''});
  const closeButton = target(), trigger = target(), form = target();
  const status = {}, results = target({replaceChildren() {}});
  const fields = {'[data-search-input]': input, '[data-search-status]': status,
    '[data-search-results]': results, '[data-search-form]': form, '[data-search-close]': closeButton};
  const dialog = target({open: false, dataset: {}, querySelector(s) { return fields[s]; },
    showModal() { this.open = true; }, close() { this.open = false; this.listeners.close(); }});
  const root = {clientWidth: 985, style: {overflow: 'auto', paddingRight: '2px'}};
  const document = target({documentElement: root, activeElement: trigger,
    querySelector(s) { return s === '[data-search-dialog]' ? dialog : trigger; }});
  const window = {innerWidth: 1000, getComputedStyle() { return {paddingRight: '2px'}; }};
  vm.runInNewContext(source, {document, window, clearTimeout, setTimeout});
  trigger.listeners.click({preventDefault() {}});
  assert.equal(root.style.overflow, 'hidden');
  assert.equal(root.style.paddingRight, '17px');
  closeButton.listeners.click();
  assert.equal(root.style.overflow, 'auto');
  assert.equal(root.style.paddingRight, '2px');
});
