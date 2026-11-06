const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');

const source = fs.readFileSync(
  path.join(__dirname, '..', 'app', 'static', 'like-button.js'),
  'utf8',
);

function createHarness({ liked = false, count = 3, fetchImpl }) {
  const state = { pressed: String(liked), classes: new Set(liked ? ['like-button--active'] : []) };
  let submitHandler;
  let nativeSubmits = 0;
  const button = {
    disabled: false,
    classList: { toggle(name, on) { on ? state.classes.add(name) : state.classes.delete(name); } },
    getAttribute: () => state.pressed,
    setAttribute(name, value) { assert.equal(name, 'aria-pressed'); state.pressed = value; },
  };
  const label = { textContent: liked ? '已点赞' : '点赞' };
  const counter = { textContent: String(count) };
  const form = {
    action: '/post/1/like',
    dataset: { labelLike: '点赞', labelLiked: '已点赞' },
    addEventListener(name, handler) { assert.equal(name, 'submit'); submitHandler = handler; },
    querySelector(selector) {
      return { '.like-button': button, '[data-like-label]': label, '.like-count': counter }[selector];
    },
    submit() { nativeSubmits += 1; },
  };
  const calls = [];
  const context = {
    document: { querySelector: (selector) => { assert.equal(selector, '[data-like-form]'); return form; } },
    window: { fetch: true },
    FormData: function () { return {}; },
    fetch: (...args) => { calls.push(args); return fetchImpl(...args); },
  };
  vm.runInNewContext(source, context);
  return {
    state, label, counter, button, calls,
    nativeSubmits: () => nativeSubmits,
    submit: () => submitHandler({ preventDefault() {} }),
  };
}

const jsonResponse = (body) => Promise.resolve({
  ok: true,
  headers: { get: () => 'application/json' },
  json: () => Promise.resolve(body),
});

test('liking updates the button from the server answer without leaving the page', async () => {
  const harness = createHarness({ fetchImpl: () => jsonResponse({ liked: true, count: 4 }) });

  await harness.submit();

  assert.equal(harness.calls[0][0], '/post/1/like');
  assert.equal(harness.calls[0][1].headers.Accept, 'application/json');
  assert.equal(harness.state.pressed, 'true');
  assert.equal(harness.state.classes.has('like-button--active'), true);
  assert.equal(harness.label.textContent, '已点赞');
  assert.equal(harness.counter.textContent, '4');
  assert.equal(harness.button.disabled, false);
  assert.equal(harness.nativeSubmits(), 0);
});

test('unliking flips it back', async () => {
  const harness = createHarness({ liked: true, count: 4, fetchImpl: () => jsonResponse({ liked: false, count: 3 }) });

  await harness.submit();

  assert.equal(harness.state.pressed, 'false');
  assert.equal(harness.label.textContent, '点赞');
  assert.equal(harness.counter.textContent, '3');
});

test('the button reacts at once and is locked while the request is in flight', async () => {
  let resolve;
  const harness = createHarness({ fetchImpl: () => new Promise((r) => { resolve = r; }) });

  const pending = harness.submit();
  assert.equal(harness.state.pressed, 'true');
  assert.equal(harness.counter.textContent, '4');
  assert.equal(harness.button.disabled, true);
  await harness.submit();
  assert.equal(harness.calls.length, 1);

  resolve({ ok: true, headers: { get: () => 'application/json' }, json: () => Promise.resolve({ liked: true, count: 4 }) });
  await pending;
  assert.equal(harness.button.disabled, false);
});

test('a failed request is undone and the form is submitted the normal way', async () => {
  const harness = createHarness({ fetchImpl: () => Promise.reject(new Error('offline')) });

  await harness.submit();

  assert.equal(harness.state.pressed, 'false');
  assert.equal(harness.counter.textContent, '3');
  assert.equal(harness.nativeSubmits(), 1);
});

test('an HTML answer (for example a login page) also falls back to a normal submit', async () => {
  const harness = createHarness({
    fetchImpl: () => Promise.resolve({ ok: true, headers: { get: () => 'text/html' } }),
  });

  await harness.submit();

  assert.equal(harness.nativeSubmits(), 1);
  assert.equal(harness.state.pressed, 'false');
});
