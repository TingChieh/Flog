const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');

const source = fs.readFileSync(
  path.join(__dirname, '..', 'app', 'static', 'like-button.js'),
  'utf8',
);

const HEART = '❤️';
const LAUGH = '\u{1f602}';
const PARTY = '\u{1f389}';

// mine: the emoji already picked; counts: what the page shows beside each emoji.
function createHarness({ mine = null, counts = {}, fetchImpl, motion = false, reduced = false }) {
  const animations = { pops: 0, rolls: 0, bumps: 0, floaters: 0, ghosts: 0, layers: [] };
  let submitHandler;
  let nativeSubmits = 0;
  const makeButton = (value) => {
    const counter = { textContent: counts[value] ? String(counts[value]) : '' };
    if (motion) {
      counter.animate = () => { animations.rolls += 1; };
      counter.parentNode = {
        style: {},
        append(child) {
          animations.ghosts += 1;
          child.animate = () => { const run = {}; Promise.resolve().then(() => run.onfinish && run.onfinish()); return run; };
        },
      };
    }
    const emoji = {};
    if (motion) emoji.animate = () => { animations.pops += 1; };
    const state = { pressed: String(mine === value), classes: new Set() };
    return {
      value,
      animate: motion ? () => { animations.bumps += 1; } : undefined,
      disabled: false,
      counter,
      state,
      classList: { toggle(name, on) { on ? state.classes.add(name) : state.classes.delete(name); } },
      getAttribute: () => state.pressed,
      setAttribute(name, val) { assert.equal(name, 'aria-pressed'); state.pressed = val; },
      querySelector(selector) {
        return { '[data-reaction-count]': counter, '[data-reaction-emoji]': emoji }[selector];
      },
      getBoundingClientRect: () => ({ left: 10, top: 20, width: 40, height: 30 }),
    };
  };
  const buttons = [HEART, LAUGH, PARTY].map(makeButton);
  const fallback = { value: '', disabled: true };
  const form = {
    action: '/post/1/like',
    addEventListener(name, handler) {
      if (name === 'submit') submitHandler = handler;
      else assert.ok(['pointerenter', 'focusin', 'touchstart'].includes(name));
    },
    querySelectorAll(selector) { assert.equal(selector, '[data-reaction]'); return buttons; },
    querySelector(selector) { assert.equal(selector, '[data-reaction-fallback]'); return fallback; },
    submit() { nativeSubmits += 1; },
  };
  const calls = [];
  const makeNode = () => {
    const node = { style: {}, children: [], setAttribute() {}, append(child) { node.children.push(child); }, remove() {} };
    node.animate = () => { animations.floaters += 1; const run = {}; Promise.resolve().then(() => run.onfinish && run.onfinish()); return run; };
    return node;
  };
  const context = {
    document: {
      querySelector: (selector) => { assert.equal(selector, '[data-like-form]'); return form; },
      ...(motion ? { createElement: makeNode, body: { append(layer) { animations.layers.push(layer); } } } : {}),
    },
    window: { fetch: true, ...(motion ? { matchMedia: () => ({ matches: reduced }) } : {}) },
    FormData: function () { const data = {}; return { set(key, value) { data[key] = value; }, data }; },
    fetch: (...args) => { calls.push(args); return fetchImpl(...args); },
  };
  vm.runInNewContext(source, context);
  const [heart, laugh, party] = buttons;
  return {
    heart, laugh, party, fallback, calls, animations,
    nativeSubmits: () => nativeSubmits,
    pick: (button) => submitHandler({ submitter: button, preventDefault() {} }),
  };
}

const jsonResponse = (body) => Promise.resolve({
  ok: true,
  headers: { get: () => 'application/json' },
  json: () => Promise.resolve(body),
});

test('picking an emoji marks it and shows the counts the server answers with', async () => {
  const harness = createHarness({
    counts: { [HEART]: 2 },
    fetchImpl: () => jsonResponse({ reaction: LAUGH, counts: { [HEART]: 2, [LAUGH]: 1, [PARTY]: 0 } }),
  });

  await harness.pick(harness.laugh);

  assert.equal(harness.calls[0][0], '/post/1/like');
  assert.equal(harness.calls[0][1].headers.Accept, 'application/json');
  assert.equal(harness.calls[0][1].body.data.emoji, LAUGH);
  assert.equal(harness.laugh.state.pressed, 'true');
  assert.equal(harness.laugh.state.classes.has('reaction--active'), true);
  assert.equal(harness.laugh.counter.textContent, '1');
  assert.equal(harness.heart.counter.textContent, '2');
  assert.equal(harness.party.counter.textContent, '');
  assert.equal(harness.laugh.disabled, false);
  assert.equal(harness.nativeSubmits(), 0);
});

test('picking another emoji moves your pick', async () => {
  const harness = createHarness({
    mine: HEART,
    counts: { [HEART]: 3 },
    fetchImpl: () => jsonResponse({ reaction: PARTY, counts: { [HEART]: 2, [LAUGH]: 0, [PARTY]: 1 } }),
  });

  await harness.pick(harness.party);

  assert.equal(harness.heart.state.pressed, 'false');
  assert.equal(harness.heart.counter.textContent, '2');
  assert.equal(harness.party.state.pressed, 'true');
  assert.equal(harness.party.counter.textContent, '1');
});

test('picking your own emoji again takes it back', async () => {
  const harness = createHarness({
    mine: LAUGH,
    counts: { [LAUGH]: 1 },
    fetchImpl: () => jsonResponse({ reaction: null, counts: { [HEART]: 0, [LAUGH]: 0, [PARTY]: 0 } }),
  });

  await harness.pick(harness.laugh);

  assert.equal(harness.laugh.state.pressed, 'false');
  assert.equal(harness.laugh.counter.textContent, '');
});

test('the buttons react at once and a second pick is ignored while the request is in flight', async () => {
  let resolve;
  const harness = createHarness({
    mine: HEART,
    counts: { [HEART]: 1 },
    fetchImpl: () => new Promise((r) => { resolve = r; }),
  });

  const pending = harness.pick(harness.laugh);
  assert.equal(harness.laugh.state.pressed, 'true');
  assert.equal(harness.laugh.counter.textContent, '1');
  assert.equal(harness.heart.state.pressed, 'false');
  assert.equal(harness.heart.counter.textContent, '');
  await harness.pick(harness.party);
  assert.equal(harness.calls.length, 1);
  assert.equal(harness.laugh.disabled, false);

  resolve({
    ok: true,
    headers: { get: () => 'application/json' },
    json: () => Promise.resolve({ reaction: LAUGH, counts: { [HEART]: 0, [LAUGH]: 1, [PARTY]: 0 } }),
  });
  await pending;
  assert.equal(harness.laugh.disabled, false);
});

test('a failed request is undone and the form is submitted the normal way with the pick', async () => {
  const harness = createHarness({
    mine: HEART,
    counts: { [HEART]: 4 },
    fetchImpl: () => Promise.reject(new Error('offline')),
  });

  await harness.pick(harness.party);

  assert.equal(harness.heart.state.pressed, 'true');
  assert.equal(harness.heart.counter.textContent, '4');
  assert.equal(harness.party.state.pressed, 'false');
  assert.equal(harness.fallback.value, PARTY);
  assert.equal(harness.fallback.disabled, false);
  assert.equal(harness.nativeSubmits(), 1);
});

test('an HTML answer (for example a login page) also falls back to a normal submit', async () => {
  const harness = createHarness({
    fetchImpl: () => Promise.resolve({ ok: true, headers: { get: () => 'text/html' } }),
  });

  await harness.pick(harness.heart);

  assert.equal(harness.nativeSubmits(), 1);
  assert.equal(harness.heart.state.pressed, 'false');
});

const answer = { reaction: LAUGH, counts: { [HEART]: 0, [LAUGH]: 1, [PARTY]: 0 } };

test('the picked emoji pops, a handful of it floats up, and the count rolls', async () => {
  const harness = createHarness({ motion: true, fetchImpl: () => jsonResponse(answer) });

  await harness.pick(harness.laugh);

  assert.equal(harness.animations.pops, 1);
  assert.equal(harness.animations.layers.length, 1);
  assert.equal(harness.animations.layers[0].children.length, 5);
  assert.equal(harness.animations.layers[0].children[0].textContent, LAUGH);
  assert.equal(harness.animations.rolls, 1);
  assert.equal(harness.animations.bumps, 1);
  assert.equal(harness.animations.ghosts, 0);
});

test('a number that changes slides the old one out while the new one slides in', async () => {
  const harness = createHarness({
    motion: true,
    counts: { [LAUGH]: 4 },
    fetchImpl: () => jsonResponse({ reaction: LAUGH, counts: { [HEART]: 0, [LAUGH]: 5, [PARTY]: 0 } }),
  });

  await harness.pick(harness.laugh);

  assert.equal(harness.animations.rolls, 1);
  assert.equal(harness.animations.ghosts, 1);
  assert.equal(harness.laugh.counter.textContent, '5');
});

test('taking a reaction back shrinks the emoji and sinks one out, with no burst', async () => {
  const harness = createHarness({
    motion: true,
    mine: LAUGH,
    counts: { [LAUGH]: 1 },
    fetchImpl: () => jsonResponse({ reaction: null, counts: { [HEART]: 0, [LAUGH]: 0, [PARTY]: 0 } }),
  });

  await harness.pick(harness.laugh);

  assert.equal(harness.animations.pops, 1);
  assert.equal(harness.animations.layers.length, 1);
  assert.equal(harness.animations.layers[0].children.length, 1);
  assert.equal(harness.animations.bumps, 1);
});

test('readers who asked for less motion get none of it', async () => {
  const harness = createHarness({ motion: true, reduced: true, fetchImpl: () => jsonResponse(answer) });

  await harness.pick(harness.laugh);

  assert.deepEqual(
    [harness.animations.pops, harness.animations.layers.length, harness.animations.rolls,
      harness.animations.bumps], [0, 0, 0, 0]);
  assert.equal(harness.laugh.state.pressed, 'true');
});

test('a browser that chokes on the animations still records the reaction without reloading the page', async () => {
  const harness = createHarness({ motion: true, fetchImpl: () => jsonResponse(answer) });
  harness.laugh.animate = () => { throw new Error('unsupported keyframes'); };
  harness.laugh.counter.animate = () => { throw new Error('unsupported keyframes'); };

  await harness.pick(harness.laugh);

  assert.equal(harness.nativeSubmits(), 0);
  assert.equal(harness.laugh.state.pressed, 'true');
  assert.equal(harness.laugh.counter.textContent, '1');
});

test('the button eases to its new width when the number goes away', async () => {
  const widths = [];
  const harness = createHarness({
    motion: true,
    mine: LAUGH,
    counts: { [LAUGH]: 1 },
    fetchImpl: () => jsonResponse({ reaction: null, counts: { [HEART]: 0, [LAUGH]: 0, [PARTY]: 0 } }),
  });
  let width = 78;
  Object.defineProperty(harness.laugh, 'offsetWidth', { get: () => width });
  harness.laugh.style = {};
  harness.laugh.animate = (frames) => {
    widths.push(frames);
    return {};
  };
  const real = harness.laugh.counter.textContent;
  Object.defineProperty(harness.laugh.counter, 'textContent', {
    get: () => real, set: (value) => { width = value === '' ? 52 : 78; }, configurable: true,
  });

  await harness.pick(harness.laugh);

  const sized = widths.find((frames) => frames[0].width);
  assert.equal(harness.laugh.style.clipPath, 'inset(-16px 0 -16px 0)');
  assert.deepEqual(JSON.parse(JSON.stringify(sized)), [{ width: '78px' }, { width: '52px' }]);
});
