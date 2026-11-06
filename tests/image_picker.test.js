const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');

const source = fs.readFileSync(
  path.join(__dirname, '..', 'app', 'static', 'image-picker.js'), 'utf8');

function createElement(tagName) {
  return {
    tagName, className: '', textContent: '', hidden: false, children: [],
    attributes: {}, dataset: {}, listeners: {}, removed: false, opened: false,
    append(...nodes) { this.children.push(...nodes); },
    replaceChildren(...nodes) { this.children = [...nodes]; },
    setAttribute(name, value) { this.attributes[name] = String(value); },
    addEventListener(name, listener) { this.listeners[name] = listener; },
    remove() { this.removed = true; },
    showModal() { this.opened = true; },
    close() { this.opened = false; if (this.listeners.close) this.listeners.close(); },
  };
}

function walk(node, visit) {
  visit(node);
  (node.children || []).forEach((child) => walk(child, visit));
}

function createHarness({ responses } = {}) {
  const requests = [];
  const created = [];
  const body = createElement('body');
  const queue = [...(responses || [{ ok: true, payload: { images: [] } }])];
  const context = {
    window: {},
    setTimeout: (fn) => { fn(); return 1; },
    clearTimeout() {},
    fetch(url, options) {
      requests.push({ url, ...options });
      const next = queue.length > 1 ? queue.shift() : queue[0];
      if (next.reject) return Promise.reject(new Error('network'));
      return Promise.resolve({ ok: next.ok, json: () => Promise.resolve(next.payload) });
    },
    document: {
      body,
      createElement(tagName) {
        const element = createElement(tagName);
        created.push(element);
        return element;
      },
    },
  };
  vm.runInNewContext(source, context);
  const find = (predicate) => {
    const found = [];
    walk(body, (node) => { if (predicate(node)) found.push(node); });
    return found;
  };
  return {
    picker: context.window.FlogImagePicker,
    requests, body, find,
    dialog: () => find((n) => n.tagName === 'dialog')[0],
    items: () => find((n) => n.className === 'image-picker__item'),
    status: () => find((n) => n.className === 'image-picker__status')[0],
    async settle() { for (let i = 0; i < 12; i += 1) await Promise.resolve(); },
  };
}

const IMAGES = [
  { id: 1, title: 'Sunset', url: '/files/a.png', thumb: '/files/_w/480/a.webp', size: 10 },
  { id: 2, title: 'Odd [name]\\', url: '/files/b.png', size: 20 },
];

test('markdownFor escapes brackets and backslashes in the title', () => {
  const { picker } = createHarness();
  assert.equal(picker.markdownFor(IMAGES[0]), '![Sunset](/files/a.png)');
  assert.equal(picker.markdownFor(IMAGES[1]), '![Odd \\[name\\]\\\\](/files/b.png)');
});

test('open shows a modal dialog and loads the images with the session cookie', async () => {
  const harness = createHarness({ responses: [{ ok: true, payload: { images: IMAGES } }] });
  harness.picker.open({ url: '/admin/images/picker', onSelect() {} });
  await harness.settle();

  assert.equal(harness.dialog().opened, true);
  assert.equal(harness.requests[0].url, '/admin/images/picker?q=');
  assert.equal(harness.requests[0].credentials, 'same-origin');
  assert.equal(harness.items().length, 2);
  const image = harness.find((n) => n.tagName === 'img')[0];
  assert.equal(image.src, '/files/_w/480/a.webp');
  assert.equal(image.loading, 'lazy');
  assert.equal(harness.find((n) => n.tagName === 'img')[1].src, '/files/b.png');
});

test('choosing an image inserts its Markdown and closes the dialog', async () => {
  const harness = createHarness({ responses: [{ ok: true, payload: { images: IMAGES } }] });
  const chosen = [];
  harness.picker.open({ url: '/p', onSelect: (markdown) => chosen.push(markdown) });
  await harness.settle();

  harness.items()[0].listeners.click();

  assert.deepEqual(chosen, ['![Sunset](/files/a.png)']);
  assert.equal(harness.dialog().opened, false);
  assert.equal(harness.dialog().removed, true);
});

test('an empty library says so', async () => {
  const harness = createHarness({ responses: [{ ok: true, payload: { images: [] } }] });
  harness.picker.open({ url: '/p', onSelect() {} });
  await harness.settle();
  assert.equal(harness.status().textContent, '没有图片');
  assert.equal(harness.items().length, 0);
});

test('a failed request shows an error and does not throw', async () => {
  for (const response of [{ reject: true }, { ok: false, payload: {} },
                          { ok: true, payload: { oops: 1 } }]) {
    const harness = createHarness({ responses: [response] });
    harness.picker.open({ url: '/p', onSelect() {} });
    await harness.settle();
    assert.equal(harness.status().textContent, '加载失败');
    assert.equal(harness.items().length, 0);
  }
});

test('typing in the search box reloads with the encoded query', async () => {
  const harness = createHarness({ responses: [
    { ok: true, payload: { images: IMAGES } },
    { ok: true, payload: { images: [IMAGES[0]] } },
  ] });
  harness.picker.open({ url: '/p', onSelect() {} });
  await harness.settle();

  const input = harness.find((n) => n.tagName === 'input')[0];
  input.value = 'sun set&';
  input.listeners.input();
  await harness.settle();

  assert.equal(harness.requests[1].url, '/p?q=sun%20set%26');
  assert.equal(harness.items().length, 1);
});

test('the close button and a backdrop click dismiss the dialog', async () => {
  const harness = createHarness();
  harness.picker.open({ url: '/p', onSelect() {} });
  await harness.settle();
  const dialog = harness.dialog();
  harness.find((n) => n.className === 'image-picker__close')[0].listeners.click();
  assert.equal(dialog.opened, false);

  const second = createHarness();
  second.picker.open({ url: '/p', onSelect() {} });
  const again = second.dialog();
  again.listeners.click({ target: again });
  assert.equal(again.opened, false);
});

test('opening twice replaces the earlier dialog', async () => {
  const harness = createHarness();
  harness.picker.open({ url: '/p', onSelect() {} });
  const first = harness.dialog();
  harness.picker.open({ url: '/p', onSelect() {} });
  assert.equal(first.removed, true);
});
