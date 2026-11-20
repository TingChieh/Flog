const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');

const source = fs.readFileSync(
  path.join(__dirname, '..', 'app', 'static', 'code-blocks.js'),
  'utf8',
);

function createButton() {
  const attrs = {};
  const listeners = {};
  return {
    type: '',
    className: '',
    textContent: '',
    attrs,
    setAttribute(name, value) { attrs[name] = value; },
    addEventListener(type, fn) { listeners[type] = fn; },
    click() { return listeners.click(); },
  };
}

function runScript({ blocks = [{ textContent: 'print(1)' }], writeText = async () => {} } = {}) {
  const appended = [];
  const pres = blocks.map((code) => ({
    querySelector: (selector) => (selector === 'code' ? code : null),
    appendChild(child) { appended.push(child); },
  }));
  const timers = [];
  const document = {
    querySelectorAll: (selector) => (selector === '.article-body pre, .page-body pre' ? pres : []),
    createElement: (tag) => (tag === 'button' ? createButton() : null),
  };
  const navigator = writeText ? { clipboard: { writeText } } : {};
  vm.runInNewContext(source, {
    document,
    navigator,
    setTimeout(fn, delay) {
      timers.push({ fn, delay });
      return timers.length;
    },
    clearTimeout() {},
  });
  return { appended, timers };
}

test('adds a copy button that copies code text and resets after 2 seconds', async () => {
  const copied = [];
  const { appended, timers } = runScript({
    blocks: [{ textContent: 'const x = 42;' }],
    writeText: async (text) => { copied.push(text); },
  });

  assert.equal(appended.length, 1);
  const button = appended[0];
  assert.equal(button.textContent, 'Copy');
  assert.equal(button.attrs['aria-label'], 'Copy code');

  await button.click();
  assert.deepEqual(copied, ['const x = 42;']);
  assert.equal(button.textContent, 'Copied!');
  assert.equal(timers[0].delay, 2000);

  timers[0].fn();
  assert.equal(button.textContent, 'Copy');
});

test('shows failure feedback when clipboard write rejects', async () => {
  const { appended } = runScript({
    blocks: [{ textContent: 'echo hi' }],
    writeText: async () => { throw new Error('denied'); },
  });

  await appended[0].click();
  assert.equal(appended[0].textContent, 'Copy failed');
});

test('skips blocks when clipboard API or code child is absent', () => {
  assert.equal(runScript({ writeText: null }).appended.length, 0);
  assert.equal(runScript({ blocks: [null] }).appended.length, 0);
});
